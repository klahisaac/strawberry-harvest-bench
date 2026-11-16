# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["bpy==4.5.3", "OpenEXR==3.4.4", "numpy==1.26.4", "pillow>=11.0"]
# ///
"""Render RGB-D images of strawberries, with box labels for a YOLO detector.

    uv run --script src/data_generator/make_dataset.py --count 200

Every image is a random cluster: 2 to 7 berries of mixed size and ripeness
hanging in front of the gutter, the plants' leaves behind them and sometimes
in front, a slightly different camera position and light. Labels come from
the renderer, so they cost nothing and are exact.

Output, in the YOLO layout (labels sit next to images, under labels/):

    data/dataset/images/{train,val}/0000.png    RGB, 640x640
    data/dataset/depth/{train,val}/0000.png     depth, 16-bit, 1 unit = 1 mm
    data/dataset/labels/{train,val}/0000.txt    one line per visible berry:
                                                class cx cy w h  (0..1)
    data/dataset/data.yaml                      classes: 0 ripe, 1 unripe
    data/camera.json                            camera intrinsics

Blender's bpy wheel needs Python 3.11, so uv runs this script in its own
environment, apart from the project's.
"""

import argparse
import json
import math
import pathlib
import time

import numpy as np

import blender_scene

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "dataset"
CLASSES = ["ripe", "unripe"]
MIN_VISIBLE_PX = 60  # a berry showing fewer pixels than this is not labelled


def random_cluster(rng: np.random.Generator) -> list[blender_scene.Berry]:
    """Berries hanging in front of the gutter, not overlapping each other."""
    berries = []
    count = rng.integers(2, 8)
    while len(berries) < count:
        ripe = rng.random() < 0.5
        berry = blender_scene.Berry(
            x=rng.uniform(-0.10, 0.18),
            y=rng.uniform(0.0, 0.22),
            z=rng.uniform(0.38, 0.60),
            radius=rng.uniform(0.010, 0.022),
            ripeness=rng.uniform(0.7, 1.0) if ripe else rng.uniform(0.0, 0.55),
            shape=int(rng.integers(0, 3)),
        )
        apart = all(math.dist((berry.x, berry.y, berry.z), (b.x, b.y, b.z)) > 1.6 * (berry.radius + b.radius)
                    for b in berries)
        if apart:
            berries.append(berry)
    return berries


def labels(index: np.ndarray, berries: list[blender_scene.Berry]) -> list[str]:
    """YOLO lines for each berry, boxed around the pixels where it shows."""
    lines = []
    for i, berry in enumerate(berries, start=1):
        rows, cols = np.nonzero(index == i)
        if len(rows) < MIN_VISIBLE_PX:
            continue
        x0, x1, y0, y1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
        w, h = blender_scene.WIDTH, blender_scene.HEIGHT
        cls = 0 if berry.ripeness >= blender_scene.RIPE_MIN else 1
        lines.append(f"{cls} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                     f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=200, help="images to render (default 200)")
    parser.add_argument("--val", type=float, default=0.2, help="share kept for validation (default 0.2)")
    parser.add_argument("--samples", type=int, default=32, help="Cycles samples per pixel (default 32)")
    parser.add_argument("--seed", type=int, default=1, help="random seed (default 1)")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    for kind in ("images", "depth", "labels"):
        for split in ("train", "val"):
            (OUT / kind / split).mkdir(parents=True, exist_ok=True)

    renderer = blender_scene.GreenhouseRenderer(args.samples, seed=args.seed)
    for n in range(args.count):
        started = time.time()
        split = "val" if n < args.count * args.val else "train"
        x, y, z = blender_scene.CAMERA_AT
        camera_at = (x + rng.uniform(-0.03, 0.03), y + rng.uniform(-0.03, 0.03), z + rng.uniform(-0.07, 0.05))
        berries = random_cluster(rng)
        name = f"{n:04d}"
        index = renderer.render(berries, OUT / "images" / split / f"{name}.png", OUT / "depth" / split / f"{name}.png",
                                seed=args.seed * 100000 + n, camera_at=camera_at,
                                leaves_in_front=int(rng.integers(0, 3)))
        found = labels(index, berries)
        (OUT / "labels" / split / f"{name}.txt").write_text("".join(line + "\n" for line in found))
        print(f"{split}/{name}: {len(berries)} berries, {len(found)} labelled, {time.time() - started:.1f} s",
              flush=True)

    (OUT / "data.yaml").write_text(
        f"path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    (ROOT / "data" / "camera.json").write_text(json.dumps(blender_scene.camera_intrinsics(), indent=2) + "\n")


if __name__ == "__main__":
    main()
