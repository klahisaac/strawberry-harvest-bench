"""The learned detector: its decoding, its option, and what it finds."""

import numpy as np
import pytest

from harvestbench import scene, scenario
from harvestbench.camera import Intrinsics, camera_pose
from harvestbench.cell import MuJoCoCell
from harvestbench.learned import (
    DEPTH_REF_M, DEPTH_SPAN_M, SIZE_SCALE_PX, STRIDE, WEIGHTS, LearnedDetector, decode,
)
from harvestbench.session import DETECTORS, match_detections
from harvestbench.train_detector import SEED0, encode_targets, training_scenario


def test_both_detectors_can_be_chosen():
    assert set(DETECTORS) == {"colour", "learned"}
    assert DETECTORS["learned"]().name == "learned"


def test_targets_decode_back_to_their_labels():
    """What training asks for and what inference reads out are the same code path."""
    label = [321.5, 187.25, 24.0, 31.0, 0.8, 0.86]
    target, mask = encode_targets([label])
    assert mask.sum() == 1
    out = target.copy()
    out[0] = np.where(target[0] == 1, 9.0, -9.0)  # heat as logits
    out[5] = np.log(target[5].clip(1e-6, 1 - 1e-6) / (1 - target[5].clip(1e-6, 1 - 1e-6)))
    (found,) = decode(out, 0.35)
    assert found["u"] == pytest.approx(label[0], abs=1e-3)
    assert found["v"] == pytest.approx(label[1], abs=1e-3)
    assert (found["w"], found["h"]) == pytest.approx((label[2], label[3]), abs=1e-3)
    assert found["ripeness"] == pytest.approx(label[4], abs=1e-3)
    assert found["z"] == pytest.approx(label[5], abs=1e-4)


def test_decode_keeps_only_peaks_above_the_threshold():
    out = np.zeros((7, 120, 160), np.float32)
    out[0] = -9.0
    # A strong peak, a weaker neighbour beside it, and one below the threshold.
    out[0, 40, 50], out[0, 40, 51], out[0, 80, 100] = 4.0, 2.0, -1.0
    found = decode(out, 0.35)
    assert len(found) == 1
    assert (found[0]["u"], found[0]["v"]) == (50 * STRIDE, 40 * STRIDE)


def test_units_are_what_the_decoder_assumes():
    assert (STRIDE, SIZE_SCALE_PX) == (4, 32.0)
    assert DEPTH_REF_M + DEPTH_SPAN_M > 1.0  # the fruit hangs inside the regressed range


def test_training_scenes_never_use_the_tier_seeds():
    """Seeds 1-40 are what the gate measures; training starts far above them."""
    assert SEED0 > 10_000
    sc = training_scenario(SEED0 + 1)  # an odd seed: a cluster scene
    assert sc.berries and all(0.28 < b.pos[1] <= 0.44 for b in sc.berries)


needs_model = pytest.mark.skipif(
    not WEIGHTS.exists(), reason="no trained weights; run harvestbench.train_detector"
)


@needs_model
def test_the_network_finds_the_fruit_on_a_held_out_gutter():
    pytest.importorskip("torch")
    sc = scenario.generate(seed=3, n_berries=6)  # a tier scenario, never trained on
    cell = MuJoCoCell(sc, seed=1, detector=LearnedDetector())
    detections = cell.observe()
    matched = match_detections(sc, detections)
    truth = {b.berry_id: b for b in sc.berries}
    found = {m for m in matched.values() if m}
    assert len(found) >= len(sc.berries) - 1
    errors = [np.linalg.norm(np.subtract(d.pos, truth[matched[d.berry_id]].pos))
              for d in detections if matched.get(d.berry_id)]
    assert np.mean(errors) < 0.015


@needs_model
def test_the_tray_check_stays_with_the_colour_detector():
    pytest.importorskip("torch")
    from harvestbench.perception import ColorThresholdDetector

    cell = MuJoCoCell(scenario.generate(seed=3, n_berries=6), seed=1)
    frame = cell.capture(scene.WRIST_CAM, 640, 480)
    intr = Intrinsics.of(cell.model, scene.WRIST_CAM, 640, 480)
    pos, mat = camera_pose(cell.model, cell.data, scene.WRIST_CAM)
    learned = LearnedDetector().detect(frame, intr, pos, mat)
    colour = ColorThresholdDetector().detect(frame, intr, pos, mat)
    assert [d.pos for d in learned] == [d.pos for d in colour]
