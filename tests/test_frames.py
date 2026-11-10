"""Trajectory sampling: the cell records the arm and fruit only when asked."""

from harvestbench import scenario
from harvestbench.cell import MuJoCoCell
from harvestbench.session import RunConfig, run_scenario


def test_frames_are_off_by_default():
    """The scenario suite runs hundreds of these; frames are only for watching."""
    sc = scenario.generate(seed=31, n_berries=4)
    cell = MuJoCoCell(sc, seed=31)
    cell.pick(cell.observe()[0])
    assert cell.frames == []


def test_frames_are_sampled_at_the_requested_rate():
    sc = scenario.generate(seed=31, n_berries=4)
    cell = MuJoCoCell(sc, seed=31, frame_hz=20.0)
    cell.pick(cell.observe()[0])
    assert len(cell.frames) > 5
    gaps = [b["t"] - a["t"] for a, b in zip(cell.frames, cell.frames[1:])]
    assert all(g > 0 for g in gaps), "time must move forward"
    assert max(gaps) < 0.12, "a 20 Hz request should not leave 100 ms holes"


def test_a_frame_carries_the_arm_and_every_berry():
    sc = scenario.generate(seed=32, n_berries=5)
    cell = MuJoCoCell(sc, seed=32, frame_hz=20.0)
    cell.pick(cell.observe()[0])
    f = cell.frames[-1]
    assert set(f["arm"]) == {"carriage", "elbow", "wrist", "cutter", "tray"}
    assert set(f["berries"]) == {b.berry_id for b in sc.berries}
    assert all(len(v) == 3 for v in f["arm"].values())


def test_phases_cover_the_attempt():
    sc = scenario.generate(seed=33, n_berries=4)
    cell = MuJoCoCell(sc, seed=33, frame_hz=30.0)
    cell.pick(cell.observe()[0])
    phases = {f["phase"] for f in cell.frames}
    assert {"standoff", "approach", "retract"} <= phases


def test_run_scenario_passes_frame_hz_through():
    sc = scenario.generate(seed=34, n_berries=4)
    off = run_scenario(sc, RunConfig(seed=34, n_berries=4))
    on = run_scenario(sc, RunConfig(seed=34, n_berries=4, frame_hz=20.0))
    assert off.frames == []
    assert len(on.frames) > 5
