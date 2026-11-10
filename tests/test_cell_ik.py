"""The arm reaches where it is told, and reports outcomes from the physics."""

import numpy as np

import mujoco

from harvestbench import cell as cellmod, scenario
from harvestbench.cell import (
    ELBOW, PERFECT_SENSOR, SHOULDER, WRIST, MuJoCoCell, level_tray,
)
from harvestbench.scene import LEAF_OCCLUSION_MIN, SURVEY_CAM

NO_NOISE = PERFECT_SENSOR


def unobstructed(n_berries: int = 6, limit: int = 80):
    """A scenario with a ripe berry that has no leaf in front of it.

    Searched rather than hardcoded: which seeds offer one depends on the leaf
    threshold, and a test pinned to a seed breaks the moment that changes.
    """
    for seed in range(limit):
        sc = scenario.generate(seed=seed, n_berries=n_berries)
        clear = [b for b in sc.berries if b.should_pick and b.occlusion <= LEAF_OCCLUSION_MIN]
        if clear:
            return sc, seed, clear[0]
    raise AssertionError(f"no unobstructed ripe berry in the first {limit} seeds")


def test_ik_reaches_every_cut_point_on_a_clear_gutter():
    sc = scenario.generate(seed=11, n_berries=6)
    cell = MuJoCoCell(sc, seed=11)
    for b in sc.berries:
        _, residual = cell.ik.solve(cell.q, np.array(b.cut_point))
        assert residual < 0.002, f"{b.berry_id} residual {residual * 1000:.1f} mm"


def test_level_tray_cancels_the_wrist_pitch():
    q = np.array([0.1, 0.0, 0.5, -1.2, 0.0])
    level_tray(q)
    assert q[WRIST] == -(q[SHOULDER] + q[ELBOW])


def test_coupling_keeps_the_tray_level_after_a_solve():
    sc = scenario.generate(seed=12, n_berries=3)
    cell = MuJoCoCell(sc, seed=12)
    q, _ = cell.ik.solve(cell.q, np.array(sc.berries[0].cut_point))
    assert abs(q[WRIST] + q[SHOULDER] + q[ELBOW]) < 1e-9


def test_a_clear_ripe_berry_gets_picked_and_packed():
    """With noise off, an unobstructed berry is cut, caught and put in its cup."""
    sc, seed, berry = unobstructed()
    cell = MuJoCoCell(sc, seed=seed, sensor=NO_NOISE)
    target = next(d for d in cell.observe() if d.berry_id == berry.berry_id)
    res = cell.pick(target)
    assert res.reached and res.cut and res.caught
    assert res.outcome == "picked"
    assert res.packed and res.placed, res.note
    assert res.impact_speed_m_s is not None
    # Bruising depends on the release height, so it is not part of "clean".
    assert not res.stem_torn and not res.knocked


def test_a_caught_berry_stays_on_the_tray_until_the_punnet():
    """The carry used to throw 113 of 117 caught berries on the floor.

    The retract lunged at a home pose that put the tray under the gutter, and
    the catch was scored before any of it. This holds the carry to arriving
    with the fruit still aboard.
    """
    sc, seed, berry = unobstructed()
    cell = MuJoCoCell(sc, seed=seed, sensor=NO_NOISE)
    target = next(d for d in cell.observe() if d.berry_id == berry.berry_id)
    res = cell.pick(target)
    assert res.caught
    assert "on the way to the punnet" not in res.note


def test_a_lower_release_lands_softer(monkeypatch):
    """The release height is the lever on bruising, and it has to move it."""
    sc, seed, berry = unobstructed()

    def landing(height):
        monkeypatch.setattr(cellmod, "RELEASE_HEIGHT_M", height)
        cell = MuJoCoCell(sc, seed=seed, sensor=NO_NOISE)
        target = next(d for d in cell.observe() if d.berry_id == berry.berry_id)
        return cell.pick(target).impact_speed_m_s

    high, low = landing(0.045), landing(0.025)
    assert low < high
    assert low < cellmod.BRUISE_SPEED_M_S


def test_the_survey_camera_cannot_see_the_punnet():
    """Adding a packing tray must not change what perception reads."""
    for seed in (1, 4, 8, 21, 33):
        cell = MuJoCoCell(scenario.generate(seed=seed, n_berries=6), seed=seed)
        frame = cell.capture(SURVEY_CAM, 640, 480)
        assert not np.isin(frame.seg, list(cell._punnet_geoms)).any(), seed


def test_harvested_berries_are_not_counted_as_knocked():
    """A berry already in the tray has moved, but that is not damage."""
    sc, seed, berry = unobstructed()
    cell = MuJoCoCell(sc, seed=seed, sensor=NO_NOISE)
    target = next(d for d in cell.observe() if d.berry_id == berry.berry_id)
    first = cell.pick(target)
    assert first.caught
    # Anything picked afterwards must not blame the berry already in the tray.
    for d in cell.observe():
        if d.berry_id == berry.berry_id:
            continue
        assert berry.berry_id not in cell.pick(d).knocked


def test_observation_is_deterministic_for_a_seed():
    sc = scenario.generate(seed=14, n_berries=6)
    a = MuJoCoCell(sc, seed=14).observe()
    b = MuJoCoCell(sc, seed=14).observe()
    assert [d.berry_id for d in a] == [d.berry_id for d in b]
    assert [d.pos for d in a] == [d.pos for d in b]


def test_occlusion_hides_some_berries():
    sc = scenario.generate(seed=15, n_berries=8)
    cell = MuJoCoCell(sc, seed=15)
    seen = {d.berry_id for d in cell.observe()}
    hidden = [b for b in sc.berries if b.berry_id not in seen]
    assert all(b.occlusion > 0 for b in hidden)


def test_telemetry_records_the_pick():
    sc = scenario.generate(seed=13, n_berries=4)
    cell = MuJoCoCell(sc, seed=13, sensor=PERFECT_SENSOR)
    cell.pick(cell.observe()[0])
    events = [r["event"] for r in cell.telemetry.records]
    assert "run.started" in events
    assert "perception.frame" in events
    assert "pick.started" in events
    assert "arm.parked" in events
    # The attempt's verdict comes last, after the arm has retracted, because
    # knocks on the way out count toward it.
    assert events[-1] in ("pick.completed", "pick.failed")
    assert events.index("arm.parked") < len(events) - 1
    assert all(r["t"] >= 0 for r in cell.telemetry.records)


def test_damage_is_detected_when_berries_are_adjacent():
    """The damage path has to be provably live.

    The generated gutter spaces berries about 19 cm apart, so the baseline never
    touches a neighbour and `damage_events` stays 0. That makes the metric
    untested, which is worse than a bad number. A hand-built cluster forces the
    detection to fire.

    The neighbour has to sit at roughly the target's cut height to be hit at
    all. At the same height as the target it is missed entirely: the cutter head
    rides above it and the tray passes below, so the end effector threads
    between the two. That is a real property of this gripper, and the reason
    damage only becomes a live metric once clustered scenarios exist.
    """
    ripe = 0.8
    pair = scenario.Scenario(
        scenario_id="cluster",
        seed=0,
        berries=(
            scenario.Berry("t0", (0.600, 0.410, 0.780), 0.018, ripe, 0.0, 0.0),
            scenario.Berry("t1", (0.630, 0.405, 0.800), 0.018, ripe, 0.0, 0.0),
        ),
    )
    cell = MuJoCoCell(pair, seed=0, sensor=NO_NOISE)
    target = next(d for d in cell.observe() if d.berry_id == "t0")
    res = cell.pick(target)
    assert res.damaged, f"a berry at cut height 3 cm away should be hit, got {res.outcome}"


def test_home_is_clear_of_the_gutter_anywhere_along_the_rail():
    """The arm takes its home shape before the carriage arrives, so the shape
    has to be clear at every rail position, not just at rail 0."""
    cell = MuJoCoCell(scenario.generate(seed=1, n_berries=6), seed=1)
    gutter = mujoco.mj_name2id(cell.model, mujoco.mjtObj.mjOBJ_GEOM, "gutter_box")
    arm = cell._strike_geoms | set(cell._tray_parts)
    for rail in np.linspace(0.0, 1.2, 13):
        q = cellmod.HOME_Q.copy()
        q[0] = rail
        cell.data.qpos[cell.ik.qadr] = q
        mujoco.mj_forward(cell.model, cell.data)
        hits = [
            k for k in cell.data.contact[: cell.data.ncon]
            if (k.geom1 == gutter and k.geom2 in arm) or (k.geom2 == gutter and k.geom1 in arm)
        ]
        assert not hits, f"arm on the gutter at rail {rail:.2f}"


def test_park_arrives_after_a_pick():
    sc, seed, berry = unobstructed()
    cell = MuJoCoCell(sc, seed=seed, sensor=NO_NOISE)
    target = next(d for d in cell.observe() if d.berry_id == berry.berry_id)
    cell.pick(target)
    assert np.abs(cell.q - cellmod.HOME_Q).max() < 0.02
