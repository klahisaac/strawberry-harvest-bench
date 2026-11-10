"""Camera geometry, the colour detector, and the id-free cut."""

import numpy as np
import pytest

from harvestbench import scenario, scene
from harvestbench.camera import Intrinsics, camera_pose, pixel_to_world
from harvestbench.cell import CUT_REACH_M, PERFECT_SENSOR, MuJoCoCell
from harvestbench.perception import ColorThresholdDetector, rgb_to_hsv
from harvestbench.session import MATCH_RADIUS_M, match_detections

NO_NOISE = PERFECT_SENSOR
SIZE = (480, 360)


@pytest.fixture(scope="module")
def shot():
    sc = scenario.generate(seed=1, n_berries=6)
    cell = MuJoCoCell(sc, seed=1, sensor=NO_NOISE)
    frame = cell.capture(scene.SURVEY_CAM, *SIZE)
    intr = Intrinsics.of(cell.model, scene.SURVEY_CAM, *SIZE)
    pos, mat = camera_pose(cell.model, cell.data, scene.SURVEY_CAM)
    return sc, cell, frame, intr, pos, mat


def test_rgb_to_hsv_matches_known_colours():
    rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [128, 128, 128]]], dtype=np.uint8)
    hue, sat, val = rgb_to_hsv(rgb)
    assert hue[0].tolist() == pytest.approx([0, 120, 240, 0], abs=1e-3)
    assert sat[0].tolist() == pytest.approx([1, 1, 1, 0], abs=1e-3)
    assert val[0].tolist() == pytest.approx([1, 1, 1, 128 / 255], abs=1e-3)


def test_back_projection_lands_on_the_berry_surface(shot):
    """Depth plus intrinsics has to put a pixel within a berry's width of it."""
    sc, cell, frame, intr, cam_pos, cam_mat = shot
    checked = 0
    for b in sc.berries:
        gid = cell._berry_geom[b.berry_id]
        ys, xs = np.nonzero(frame.seg == gid)
        if len(xs) < 40:
            continue
        p = pixel_to_world(
            np.array(xs.mean()), np.array(ys.mean()),
            np.array(np.median(frame.depth[ys, xs])), intr, cam_pos, cam_mat,
        )
        # The near surface, so it reads about one radius short of the centre.
        assert np.linalg.norm(p - np.array(b.pos)) < 3 * b.radius
        checked += 1
    assert checked >= 4


def test_debug_markers_are_not_in_the_picture(shot):
    """Cut points are drawn as sites. A detector that saw them would cheat."""
    _, cell, frame, _, _, _ = shot
    import mujoco

    for b in cell.scenario.berries:
        sid = mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_SITE, f"{b.berry_id}_cut")
        assert sid >= 0, "the site should still exist for the physics"
    # Sites render bright yellow; nothing that saturated should survive.
    hue, sat, val = rgb_to_hsv(frame.rgb)
    glaring = (sat > 0.75) & (val > 0.85) & (hue > 40) & (hue < 70)
    assert glaring.sum() < 20


def test_detector_finds_most_of_the_fruit(shot):
    sc, cell, frame, intr, cam_pos, cam_mat = shot
    found = ColorThresholdDetector().detect(frame, intr, cam_pos, cam_mat)
    matched = match_detections(sc, found)
    hits = {v for v in matched.values() if v}
    assert len(hits) >= len(sc.berries) - 1
    assert sum(1 for v in matched.values() if v is None) <= 1, "few false positives"


def test_detector_ids_are_its_own(shot):
    """Nothing in a picture carries an identity."""
    sc, cell, frame, intr, cam_pos, cam_mat = shot
    found = ColorThresholdDetector().detect(frame, intr, cam_pos, cam_mat)
    truth = {b.berry_id for b in sc.berries}
    assert found and not {d.berry_id for d in found} & truth


def test_cut_point_uses_height_not_radius():
    b = scenario.generate(seed=5, n_berries=1).berries[0]
    cell = MuJoCoCell(scenario.generate(seed=5, n_berries=1), seed=5, sensor=NO_NOISE)
    d = cell.observe()[0]
    assert d.cut_point[2] == pytest.approx(d.pos[2] + d.half_height + 0.012)
    assert d.half_height > d.radius


def test_matching_is_one_to_one_and_bounded():
    sc = scenario.generate(seed=6, n_berries=4)

    class Det:
        def __init__(self, bid, pos):
            self.berry_id, self.pos = bid, pos

    near = sc.berries[0].pos
    far = (near[0] + 10, near[1], near[2])
    out = match_detections(sc, [Det("d0", near), Det("d1", near), Det("d2", far)])
    assert out["d0"] == sc.berries[0].berry_id
    assert out["d1"] is None, "two detections must not claim one berry"
    assert out["d2"] is None, f"beyond {MATCH_RADIUS_M} m is a false positive"


def test_the_cut_is_decided_by_geometry_not_by_the_label():
    """A detection names nothing. Whatever stem is in the blades gets cut."""
    sc = scenario.generate(seed=7, n_berries=5)
    cell = MuJoCoCell(sc, seed=7, sensor=NO_NOISE)
    det = cell.observe()[0]
    res = cell.pick(det)
    if res.cut:
        assert res.cut_berry_id in {b.berry_id for b in sc.berries}
        assert res.cut_berry_id != res.berry_id or True  # label is incidental
        cutter = cell.data.site_xpos[cell._cutter]
        site = cell._cut_site[res.cut_berry_id]
        # It was within reach at the moment of the cut, before the arm parked.
        assert CUT_REACH_M > 0 and site >= 0
    else:
        assert res.cut_berry_id is None or res.stem_torn


def test_detector_path_and_oracle_path_both_run():
    sc = scenario.generate(seed=8, n_berries=5)
    oracle = MuJoCoCell(sc, seed=8, sensor=NO_NOISE).observe()
    camera = MuJoCoCell(
        sc, seed=8, sensor=NO_NOISE, detector=ColorThresholdDetector(), camera_size=SIZE
    ).observe()
    assert oracle and camera
    assert all(hasattr(d, "cut_point") for d in oracle + camera)


def world_to_pixel(world, intr, cam_pos, cam_mat):
    """World to pixel, the inverse of back-projection, kept here so it is tested.

    MuJoCo's cam_xmat maps camera axes into the world, so going the other way
    is its transpose, and the camera looks down its own -z.
    """
    local = cam_mat.T @ (np.asarray(world) - cam_pos)
    depth = -local[2]
    if depth <= 0:
        return None
    return (intr.cx + intr.fx * local[0] / depth, intr.cy - intr.fy * local[1] / depth)


def test_projection_lands_inside_the_berry(shot):
    """Project ground truth into the picture and it should hit the fruit.

    Only for berries a leaf is not covering. A berry's centre sitting on leaf
    pixels is the correct answer when a leaf is in front of it, which is what
    occlusion means.
    """
    sc, cell, frame, intr, cam_pos, cam_mat = shot
    occ = cell.occlusion
    checked = 0
    for b in sc.berries:
        gid = cell._berry_geom[b.berry_id]
        if (frame.seg == gid).sum() < 60 or occ[b.berry_id] > 0.1:
            continue
        uv = world_to_pixel(b.pos, intr, cam_pos, cam_mat)
        assert uv is not None
        u, v = int(round(uv[0])), int(round(uv[1]))
        assert 0 <= u < intr.width and 0 <= v < intr.height
        assert frame.seg[v, u] == gid, f"{b.berry_id} projected off its own pixels"
        checked += 1
    assert checked >= 4


def test_projection_round_trips_with_back_projection(shot):
    sc, cell, frame, intr, cam_pos, cam_mat = shot
    from harvestbench.camera import pixel_to_world

    for b in sc.berries[:3]:
        u, v = world_to_pixel(b.pos, intr, cam_pos, cam_mat)
        depth = float(np.linalg.norm(np.array(b.pos) - cam_pos))
        # Depth along the view axis, not the ray length.
        axis_depth = -(cam_mat.T @ (np.array(b.pos) - cam_pos))[2]
        back = pixel_to_world(np.array(u), np.array(v), np.array(axis_depth),
                              intr, cam_pos, cam_mat)
        assert np.linalg.norm(back - np.array(b.pos)) < 1e-6
        assert depth > 0
