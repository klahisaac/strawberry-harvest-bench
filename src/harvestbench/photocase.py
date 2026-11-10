"""The demo's field failure: a ripe berry with an unripe one hanging in front.

It starts from a photograph taken in the field — `web/demo/field-photo.png` —
and turns it into a scene the simulator can run:

  1. measure the photo: colour picks out the ripe (red) and unripe (pale) fruit,
     and gives each one's centre and size in pixels
  2. scale: the ripe berry is taken to be 20 mm across the radius, which fixes
     metres per pixel for everything else in the picture
  3. depth: a photo has none. The unripe berry overlaps the ripe one, so it is
     in front; it is placed 50 mm in front, an assumption stated here and on
     the demo page rather than hidden

Everything the demo shows about this case runs through `run()`, with whatever
code is importable — the original tree or the copy an LLM has just edited —
so the before and after are the same experiment on different code.

This file is part of the experiment, not of the robot. The fix belongs in the
robot's code (cell.py, policy.py, perception.py); changing this file to make
the case pass would be changing the question.
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys

import mujoco
import numpy as np
from scipy import ndimage

from .scenario import Berry, Scenario

ROOT = Path(__file__).resolve().parents[2]
PHOTO = ROOT / "web" / "demo" / "field-photo.png"

# Where the photographed cluster hangs on the bench's gutter (metres).
ANCHOR = (0.60, 0.425, 0.775)  # the ripe berry's centre
RIPE_RADIUS_M = 0.020  # assumed; sets the scale of the whole photo
FRONT_DEPTH_M = 0.070  # assumed: how far in front the overlapping fruit hangs
RIPE_TARGET = "ripe"


# ---- reading the photo -----------------------------------------------------


def read_photo(path: Path = PHOTO) -> np.ndarray:
    """Any PNG, decoded by the bundled ffmpeg, as (h, w, 3) uint8."""
    import imageio_ffmpeg

    probe = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    # ffmpeg does not say the size on stdout; read it from the PNG header.
    head = Path(path).read_bytes()[16:24]
    w, h = int.from_bytes(head[:4], "big"), int.from_bytes(head[4:], "big")
    return np.frombuffer(probe.stdout, np.uint8).reshape(h, w, 3).copy()


@dataclass(frozen=True)
class Blob:
    """One berry found in the photo, in pixels."""

    kind: str  # "ripe" or "unripe"
    cx: float
    cy: float
    width: float
    height: float
    area: int
    clipped: bool  # touches the edge of the picture


def measure(rgb: np.ndarray) -> list[Blob]:
    """Ripe and unripe fruit in the photo, by colour."""
    from .perception import rgb_to_hsv

    hue, sat, val = rgb_to_hsv(rgb)
    masks = {
        "ripe": ((hue < 25) | (hue > 330)) & (sat > 0.45) & (val > 0.3),
        "unripe": (hue > 40) & (hue < 80) & (sat > 0.15) & (sat < 0.55) & (val > 0.55),
    }
    h, w = rgb.shape[:2]
    out = []
    for kind, m in masks.items():
        m = ndimage.binary_opening(m, np.ones((3, 3)))
        labels, n = ndimage.label(m)
        for i in range(1, n + 1):
            ys, xs = np.nonzero(labels == i)
            if len(xs) < 60:
                continue
            out.append(Blob(
                kind=kind, cx=float(xs.mean()), cy=float(ys.mean()),
                width=float(xs.max() - xs.min() + 1), height=float(ys.max() - ys.min() + 1),
                area=len(xs),
                clipped=bool(xs.min() == 0 or ys.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1),
            ))
    return out


def scenario_from_photo(blobs: list[Blob]) -> tuple[Scenario, dict]:
    """The photographed cluster as berries on the bench's gutter.

    The ripe berry fixes the scale and the anchor. Unripe berries that overlap
    it are in front of it; the rest hang beside it, at its depth. A berry cut
    off by the picture's edge keeps its measured centre, and its size comes
    from the unclipped direction.
    """
    ripe = max((b for b in blobs if b.kind == "ripe"), key=lambda b: b.area)
    m_per_px = RIPE_RADIUS_M / (ripe.width / 2)
    ax, ay, az = ANCHOR
    berries, notes = [], {}
    for i, b in enumerate(sorted(blobs, key=lambda b: (b.kind != "ripe", -b.area))):
        dx = (b.cx - ripe.cx) * m_per_px
        dz = -(b.cy - ripe.cy) * m_per_px  # image rows run downward
        size_px = max(b.width, b.height / 1.35) if b.clipped else b.width
        radius = float(np.clip(size_px / 2 * m_per_px, 0.012, 0.024))
        overlaps = b is not ripe and (abs(b.cx - ripe.cx) < (b.width + ripe.width) / 2
                                      and abs(b.cy - ripe.cy) < (b.height + ripe.height) / 2)
        y = ay - FRONT_DEPTH_M if overlaps else ay
        bid = RIPE_TARGET if b is ripe else f"unripe{i}"
        berries.append(Berry(
            berry_id=bid,
            pos=(ax + dx, y, az + dz),
            radius=radius,
            ripeness=0.86 if b.kind == "ripe" else 0.18,
            peduncle_yaw=0.0,
            occlusion=0.0,
        ))
        notes[bid] = {"blob": asdict(b), "in_front": overlaps}
    sc = Scenario(scenario_id="FIELD-0417", seed=417, berries=tuple(berries))
    return sc, {"m_per_px": m_per_px, "berries": notes}


def photo_scenario() -> tuple[Scenario, list[Blob], dict]:
    blobs = measure(read_photo())
    sc, info = scenario_from_photo(blobs)
    return sc, blobs, info


# ---- rendering ---------------------------------------------------------------


class Film:
    """Renders the cell from a free camera while it steps, then encodes MP4."""

    def __init__(self, model, width=768, height=432, fps=24, slow=3.0,
                 lookat=(0.57, 0.33, 0.80), distance=0.62, azimuth=140.0, elevation=-18.0):
        # MuJoCo's free camera looks along (cos el cos az, cos el sin az, sin el),
        # so azimuth 90 faces +y: from the aisle toward the gutter.
        self.renderer = mujoco.Renderer(model, height, width)
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.lookat[:] = lookat
        self.cam.distance, self.cam.azimuth, self.cam.elevation = distance, azimuth, elevation
        self.opt = mujoco.MjvOption()
        self.opt.sitegroup[:] = 0  # the cut-point markers are the simulator's answer key
        self.opt.geomgroup[3] = 1  # the arm: hidden by default, and the film is about it
        # The servos are quick: a whole attempt is a second or two of sim
        # time. Sampling `slow` times faster than the playback rate gives slow
        # motion a person can follow.
        self.fps, self.slow, self.frames, self._next = fps, slow, [], 0.0

    def shot(self, data) -> np.ndarray:
        self.renderer.update_scene(data, camera=self.cam, scene_option=self.opt)
        return self.renderer.render().copy()

    def maybe(self, data) -> None:
        if data.time >= self._next:
            self._next = data.time + 1.0 / (self.fps * self.slow)
            self.frames.append(self.shot(data))

    def write(self, path: Path, hold_s: float = 1.0) -> Path:
        import imageio_ffmpeg

        path.parent.mkdir(parents=True, exist_ok=True)
        h, w = self.frames[0].shape[:2]
        proc = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(self.fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-crf", "23", str(path)],
            stdin=subprocess.PIPE,
        )
        # Hold the last frame, so the outcome stays on screen.
        for f in self.frames + [self.frames[-1]] * int(hold_s * self.fps):
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
        proc.wait()
        return path


def close_up(sc: Scenario, path: Path) -> Path:
    """The simulated cluster from where the photographer stood."""
    from .cell import MuJoCoCell
    from .imaging import write_png

    cell = MuJoCoCell(sc, seed=0)
    ripe = next(b for b in sc.berries if b.berry_id == RIPE_TARGET)
    film = Film(cell.model, width=380, height=428, lookat=(ripe.pos[0], ripe.pos[1], ripe.pos[2] + 0.02),
                distance=0.19, azimuth=90.0, elevation=-4.0)
    return write_png(path, film.shot(cell.data))


# ---- the experiment --------------------------------------------------------


def run(out_dir: Path, video: bool = True) -> dict:
    """The robot works the photographed cluster with the importable code.

    Perception reads the survey camera, the policy chooses, the cell picks —
    the same loop as every other scenario. What comes back is what the field
    log would say, plus what the simulator knows: which berry was cut, whether
    the unripe one was hit.
    """
    from .cell import MuJoCoCell
    from .session import DETECTORS, POLICIES, match_detections

    sc, _, _ = photo_scenario()
    cell = MuJoCoCell(sc, seed=1, detector=DETECTORS["colour"]())
    film = Film(cell.model, slow=2.0) if video else None
    if film:
        step = cell._maybe_frame

        def frame():
            step()
            film.maybe(cell.data)

        cell._maybe_frame = frame
    detections = cell.observe()
    matched = match_detections(sc, detections)
    targets = POLICIES["baseline"]().choose(detections)
    attempts = []
    for t in targets:
        res = cell.pick(t)
        attempts.append({
            "label": t.berry_id, "aimed_at": matched.get(t.berry_id), "outcome": res.outcome,
            "cut": res.cut_berry_id, "knocked": list(res.knocked), "note": res.note,
            "error_mm": round(res.ik_error_m * 1000, 1), "packed": res.packed,
            "peak_force_n": round(res.peak_force_n, 2), "duration_s": round(res.duration_s, 2),
        })
    ripe_attempt = next((a for a in attempts if a["aimed_at"] == RIPE_TARGET), None)
    harvested = bool(ripe_attempt and ripe_attempt["cut"] == RIPE_TARGET
                     and ripe_attempt["packed"])
    hurt = sorted({k for a in attempts for k in a["knocked"]}
                  | {a["cut"] for a in attempts if a["cut"] and a["cut"] != RIPE_TARGET}
                  | {a["cut"] for a in attempts if a["outcome"] == "stem_torn" and a["cut"]})
    result = {
        "detections": [{"label": d.berry_id, "berry": matched.get(d.berry_id),
                        "ripeness": round(d.ripeness, 2)} for d in detections],
        "attempts": attempts,
        "harvested": harvested,
        "damaged": hurt,
        "passed": harvested and not hurt,
        "events": cell.telemetry.records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    if film and film.frames:
        film.write(out_dir / "attempt.mp4")
        result["video"] = "attempt.mp4"
    (out_dir / "result.json").write_text(json.dumps(result, indent=1))
    return result


def film_scenario(seed: int, out_dir: Path, picks: int = 2) -> dict:
    """A generated scenario, its first few attempts on film, with the importable code.

    The smoke test's picture: berries hanging clear, stems in view, picked the
    ordinary way. A fix that broke ordinary picking shows here first.
    """
    from .cell import MuJoCoCell
    from .scenario import generate
    from .session import DETECTORS, POLICIES, match_detections

    sc = generate(seed=seed, n_berries=6, scenario_id=f"S{seed:04d}")
    cell = MuJoCoCell(sc, seed=1, detector=DETECTORS["colour"]())
    detections = cell.observe()
    matched = match_detections(sc, detections)
    targets = POLICIES["baseline"]().choose(detections)[:picks]
    xs = [t.pos[0] for t in targets] or [0.3]
    film = Film(cell.model, lookat=(float(np.mean(xs)), 0.33, 0.80),
                distance=0.62 + 0.8 * float(np.ptp(xs)), azimuth=140.0, elevation=-18.0,
                slow=1.0)  # ordinary picking, carry and packing: real time is enough
    step = cell._maybe_frame

    def frame():
        step()
        film.maybe(cell.data)

    cell._maybe_frame = frame
    attempts = []
    for t in targets:
        res = cell.pick(t)
        attempts.append({"label": t.berry_id, "aimed_at": matched.get(t.berry_id),
                         "outcome": res.outcome, "packed": res.packed,
                         "knocked": list(res.knocked), "note": res.note})
    out_dir.mkdir(parents=True, exist_ok=True)
    film.write(out_dir / "smoke.mp4")
    result = {"scenario": sc.scenario_id, "attempts": attempts, "video": "smoke.mp4"}
    (out_dir / "result.json").write_text(json.dumps(result, indent=1))
    return result


def main(argv=None) -> None:
    import argparse

    p = argparse.ArgumentParser(prog="python -m harvestbench.photocase")
    p.add_argument("cmd", choices=["run", "check", "film"])
    p.add_argument("--out", type=Path, default=ROOT / "runs" / "photocase")
    p.add_argument("--no-video", dest="video", action="store_false")
    p.add_argument("--seed", type=int, default=25, help="film: the scenario to film")
    p.add_argument("--picks", type=int, default=2, help="film: how many attempts")
    args = p.parse_args(argv)
    if args.cmd == "film":
        res = film_scenario(args.seed, args.out, args.picks)
        for a in res["attempts"]:
            print(f"{a['label']} -> {a['aimed_at']}: {a['outcome']}")
        return
    res = run(args.out, video=args.video and args.cmd == "run")
    for a in res["attempts"]:
        print(f"{a['label']} -> {a['aimed_at']}: {a['outcome']}"
              f"{'  cut ' + a['cut'] if a['cut'] else ''}"
              f"{'  knocked ' + ','.join(a['knocked']) if a['knocked'] else ''}"
              f"  {a['note']}")
    verdict = "PASS" if res["passed"] else "FAIL"
    print(f"\nripe berry harvested: {res['harvested']}  fruit damaged: {res['damaged'] or 'none'}")
    print(verdict)
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
