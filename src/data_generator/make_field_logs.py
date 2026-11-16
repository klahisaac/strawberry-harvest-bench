# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = ["bpy==4.5.3", "OpenEXR==3.4.4", "numpy==1.26.4", "pillow>=11.0"]
# ///
"""Make the field data: ten harvest attempts by the robot, nine good and one not.

    uv run --script src/data_generator/make_field_logs.py

Each attempt is one log line and one RGB-D image, taken by the robot's camera
just before it picks. The pick id ties them together: the line with
"pick": "p07" goes with images/p07_rgb.png and images/p07_depth.png.

The failed attempt, p07, is a ripe berry with an unripe one hanging 70 mm in
front of it, over the ripe berry's top, where its stem is cut. The robot went
straight in and its cutter hit the unripe berry: the force on it went over
the limit and the robot stopped the attempt.

Output:

    data/field/harvest_log.jsonl          one JSON object per attempt
    data/field/images/pNN_rgb.png         RGB, 640x640
    data/field/images/pNN_depth.png       depth, 16-bit, 1 unit = 1 mm
    data/camera.json                      camera intrinsics
"""

import datetime
import json
import pathlib

import numpy as np

import blender_scene

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "field"
FAILED_PICK = 7
START = datetime.datetime(2026, 11, 9, 6, 0, 0, tzinfo=datetime.timezone.utc)
CAMERA_DISTANCE = 0.32  # the robot stops its camera this far in front of the target

Berry = blender_scene.Berry


def good_cluster(rng: np.random.Generator) -> list[Berry]:
    """A ripe target with a clear stem; neighbours only beside or behind it."""
    target = Berry(x=rng.uniform(0.02, 0.06), y=rng.uniform(0.04, 0.08), z=rng.uniform(0.48, 0.52),
                   radius=rng.uniform(0.017, 0.022), ripeness=rng.uniform(0.8, 0.95), shape=int(rng.integers(0, 3)))
    berries = [target]
    for side in rng.permutation([-1, 1])[: rng.integers(1, 3)]:
        berries.append(Berry(
            x=target.x + side * rng.uniform(0.05, 0.08), y=target.y + rng.uniform(-0.04, 0.05),
            z=target.z + rng.uniform(-0.01, 0.04), radius=rng.uniform(0.010, 0.016),
            ripeness=rng.uniform(0.0, 0.4) if rng.random() < 0.7 else rng.uniform(0.7, 0.9),
            shape=int(rng.integers(0, 3)),
        ))
    if rng.random() < 0.5:  # one more, behind the target
        berries.append(Berry(x=target.x + rng.uniform(-0.03, 0.03), y=target.y + rng.uniform(-0.01, 0.03),
                             z=target.z + 0.06, radius=0.012, ripeness=rng.uniform(0.0, 0.3)))
    return berries


def failed_cluster() -> list[Berry]:
    """The field failure: an unripe berry 70 mm in front, covering the ripe one's top."""
    ripe = Berry(x=0.04, y=0.05, z=0.50, radius=0.020, ripeness=0.86)
    in_front = Berry(x=0.042, y=0.020, z=0.43, radius=0.016, ripeness=0.15, shape=1)
    left = Berry(x=0.005, y=0.05, z=0.51, radius=0.012, ripeness=0.15, shape=2)
    right = Berry(x=0.075, y=0.015, z=0.52, radius=0.012, ripeness=0.15, shape=1)
    return [ripe, in_front, left, right]


def log_line(pick: int, when: datetime.datetime, target: Berry, rng: np.random.Generator) -> dict:
    """What the robot reported for one attempt."""
    failed = pick == FAILED_PICK
    return {
        "robot": "harvester-01",
        "row": "G3",
        "pick": f"p{pick:02d}",
        "event": "pick.aborted" if failed else "pick.completed",
        "outcome": "collision" if failed else "picked",
        "est_ripeness": round(target.ripeness + rng.uniform(-0.03, 0.03), 2),
        # Peak force on berries other than the target; the robot stops above 5 N.
        "peak_force_n": 51.8 if failed else round(rng.uniform(0.0, 0.8), 1),
        "cycle_s": 3.3 if failed else round(rng.uniform(4.3, 4.9), 1),
        "flags": ["force_limit"] if failed else [],
        "abnormal": failed,
        "time": when.isoformat(timespec="seconds"),
    }


def main() -> None:
    rng = np.random.default_rng(20261109)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    renderer = blender_scene.GreenhouseRenderer(samples=64, seed=7)
    when = START
    lines = []
    for pick in range(1, 11):
        berries = failed_cluster() if pick == FAILED_PICK else good_cluster(rng)
        target = berries[0]
        # The camera stops in front of the target, a little below it.
        camera_at = (target.x, target.y + 0.01, target.z - CAMERA_DISTANCE)
        name = f"p{pick:02d}"
        renderer.render(berries, OUT / "images" / f"{name}_rgb.png", OUT / "images" / f"{name}_depth.png",
                        seed=pick, camera_at=camera_at)

        line = log_line(pick, when, target, rng)
        lines.append(line)
        print(json.dumps(line), flush=True)
        when += datetime.timedelta(seconds=round(line["cycle_s"] + float(rng.uniform(4, 9))))

    (OUT / "harvest_log.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    (ROOT / "data" / "camera.json").write_text(json.dumps(blender_scene.camera_intrinsics(), indent=2) + "\n")


if __name__ == "__main__":
    main()
