"""The demo's field photo, turned into a scene, and the plumbing around it."""

import subprocess
import sys

from harvestbench import photocase
from harvestbench.cell import MuJoCoCell
from harvestbench.session import DETECTORS, match_detections


def test_the_photo_has_one_ripe_berry_and_three_unripe():
    blobs = photocase.measure(photocase.read_photo())
    kinds = sorted(b.kind for b in blobs)
    assert kinds == ["ripe", "unripe", "unripe", "unripe"]


def test_the_unripe_berry_over_the_ripe_one_hangs_in_front_of_it():
    sc, _, info = photocase.photo_scenario()
    ripe = next(b for b in sc.berries if b.berry_id == photocase.RIPE_TARGET)
    front = [b for b in sc.berries if info["berries"][b.berry_id]["in_front"]]
    assert len(front) == 1
    assert abs((ripe.pos[1] - front[0].pos[1]) - photocase.FRONT_DEPTH_M) < 1e-9
    # It covers the top of the ripe berry, where the stem is cut.
    assert front[0].pos[2] > ripe.pos[2]


def test_the_detector_keeps_the_ripe_berry_apart_from_the_unripe_one_in_front():
    """Run together, the two came out as one blob read as unripe, and the ripe
    berry was never attempted. The colour split is what lets the robot try."""
    sc, _, _ = photocase.photo_scenario()
    cell = MuJoCoCell(sc, seed=1, detector=DETECTORS["colour"]())
    detections = cell.observe()
    matched = match_detections(sc, detections)
    ripe = [d for d in detections if matched.get(d.berry_id) == photocase.RIPE_TARGET]
    assert len(ripe) == 1 and ripe[0].ripeness > 0.6


def test_the_cli_runs_as_a_module():
    """`python -m harvestbench.cli` did nothing and exited 0, which made the
    demo's smoke check pass without running."""
    out = subprocess.run([sys.executable, "-m", "harvestbench.cli", "--help"],
                         capture_output=True, text=True)
    assert out.returncode == 0 and "usage" in out.stdout
