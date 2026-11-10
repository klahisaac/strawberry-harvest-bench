"""The scenario is reproducible and the scene it builds is physically sane."""

import mujoco
import numpy as np
import pytest

from harvestbench import scenario, scene


def test_same_seed_same_scenario():
    a = scenario.generate(seed=7, n_berries=5)
    b = scenario.generate(seed=7, n_berries=5)
    assert a == b


def test_different_seed_differs():
    a = scenario.generate(seed=7, n_berries=5)
    b = scenario.generate(seed=8, n_berries=5)
    assert a.berries != b.berries


def test_berry_rng_is_per_berry_and_stable():
    sc = scenario.generate(seed=3, n_berries=4)
    first = [b.rng(3).random() for b in sc.berries]
    again = [b.rng(3).random() for b in sc.berries]
    assert first == again
    assert len(set(first)) == len(first), "each berry needs its own stream"


def test_should_pick_matches_ripeness_window():
    sc = scenario.generate(seed=5, n_berries=8)
    for b in sc.berries:
        expected = scenario.RIPE_MIN <= b.ripeness < scenario.OVERRIPE
        assert b.should_pick is expected


def test_cut_point_sits_above_the_berry():
    b = scenario.generate(seed=1, n_berries=1).berries[0]
    assert b.cut_point[2] > b.pos[2] + b.radius
    assert b.cut_point[:2] == b.pos[:2]


def test_scene_compiles_with_one_weld_per_berry():
    sc = scenario.generate(seed=2, n_berries=6)
    model = mujoco.MjModel.from_xml_string(scene.build(sc))
    assert model.neq == len(sc.berries)
    assert model.nu == len(scene.ARM_JOINTS)


def test_welds_hold_the_berries_still():
    """A berry that sags on its own would read as damage on every pick."""
    sc = scenario.generate(seed=4, n_berries=6)
    model = mujoco.MjModel.from_xml_string(scene.build(sc))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    bodies = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, b.berry_id) for b in sc.berries
    ]
    home = data.xpos[bodies].copy()
    for _ in range(1000):  # 2 s
        mujoco.mj_step(model, data)
    drift = np.linalg.norm(data.xpos[bodies] - home, axis=1).max()
    assert drift < 0.003, f"berries drifted {drift * 1000:.1f} mm while attached"


@pytest.mark.parametrize("seed", [1, 2])
def test_cutting_the_weld_drops_the_berry(seed):
    sc = scenario.generate(seed=seed, n_berries=3)
    model = mujoco.MjModel.from_xml_string(scene.build(sc))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    target = sc.berries[0].berry_id
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, target)
    eq = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, f"{target}_stem")
    z0 = data.xpos[body][2]
    data.eq_active[eq] = 0
    for _ in range(1000):
        mujoco.mj_step(model, data)
    assert data.xpos[body][2] < z0 - 0.2, "the cut berry should fall"
