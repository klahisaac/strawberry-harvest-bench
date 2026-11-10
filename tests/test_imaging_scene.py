"""The PNG reader, and building a scene from a given set of leaves."""

import numpy as np

from harvestbench import scene
from harvestbench.imaging import read_png, write_png
from harvestbench.scenario import generate


def test_png_round_trips(tmp_path):
    rgb = np.random.default_rng(0).integers(0, 256, (7, 5, 3), dtype=np.uint8)
    assert np.array_equal(read_png(write_png(tmp_path / "x.png", rgb)), rgb)


def test_a_given_leaf_list_replaces_the_generated_one():
    sc = generate(21)
    mjcf = scene.build(sc, leaf_boxes=[{"berry_id": "r00", "pos": (0.1, 0.36, 0.77),
                                        "half": (0.02, 0.004, 0.02)}])
    assert "r00_leafgeom" in mjcf
    assert "b00_leafgeom" not in mjcf
