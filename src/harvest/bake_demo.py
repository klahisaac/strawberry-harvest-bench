"""Build the demo page's data: run every step for real and write web/demo/.

    MUJOCO_GL=egl uv run --group demo python src/harvest/bake_demo.py             # agent included
    MUJOCO_GL=egl uv run --group demo python src/harvest/bake_demo.py --no-agent  # reuse its last copy

Steps, in the order the page shows them:

  1. the field log and each attempt's RGB-D image
  2. the failed attempt's image turned into a simulation: the berries found
  3. every attempt rerun in the simulator with the robot code as it is
  4. an AI agent (Claude Code, headless) fixes robot_controller.py in a copy
  5. every attempt rerun with the agent's code
  6. the agent's pull request text

Everything the page shows is written to web/demo/data.js and next to it.
"""

import argparse
import datetime
import difflib
import importlib.util
import json
import pathlib
import platform
import shutil
import subprocess
import time

import imageio_ffmpeg
import mujoco
import numpy as np
from PIL import Image as pil_image

import reproduce_scene

ROOT = reproduce_scene.ROOT
HERE = pathlib.Path(__file__).resolve().parent
WEB = ROOT / "web" / "v3" / "demo"  # this pipeline is version 3 of the demo; web/v1 and web/v2 are kept as recorded
WORK = ROOT / "runs" / "demo" / "work"  # the agent's copy of the code
ORIGINAL = ROOT / "runs" / "demo" / "original"  # the code as the agent was given it, to diff against
FAILED_PICK = "p07"
MODEL = "claude-opus-5-5"
AGENT_TIMEOUT_S = 30 * 60

PROMPT = """You are working on the control software of a strawberry-harvesting robot: a 6-axis arm with a cutter.

Field report from harvester-01, gutter row G3:
  pick {pick} aborted: {outcome}. The cutter touched a fruit with {force} N. It may touch only stems,
  so the robot stopped, backed out and gave up the berry after {cycle} s.
  The robot went for a ripe strawberry. An unripe strawberry hangs in front of it, over the ripe
  one's top, where the stem is cut.

Every logged attempt has been rebuilt in a MuJoCo simulation from the robot's own RGB-D image.
Run ./check.sh to see all ten, run with the robot code in this directory.

Your task: change the robot's code so that {pick} is picked, and the nine attempts that were
picked still are.

Rules:
- Change only src/harvest/robot_controller.py. The simulator (src/harvest/reproduce_scene.py)
  and the data are the experiment; do not change them.
- Keep the change small and easy to read.
- When ./check.sh says "10 of 10 attempts picked", stop. Finish with a short explanation of
  what was wrong and what you changed, then:
  PR-TITLE: <one line>
  PR-BODY:
  <markdown: a few bullets>
"""

# Claude Code still reads the presenter's own ~/.claude/CLAUDE.md, which asks for an English
# check on every reply. The agent's replies go on the page as they are, so it is told not to.
UNATTENDED = ("This is an unattended run: your replies are published on a demo page exactly as you write "
              "them. Do not correct, rate or comment on the English of the prompt, whatever other "
              "instructions say; answer only the task.")

CHECK_SH = """#!/bin/sh
# Every logged attempt, rebuilt in the simulator and run with the robot code in this copy.
cd "$(dirname "$0")/src/harvest" && exec uv run --project {root} python reproduce_scene.py
"""


def log(message: str) -> None:
    print(f"[bake] {message}", flush=True)


# ---- 1. field data ----------------------------------------------------------------


def depth_picture(depth_mm: np.ndarray) -> np.ndarray:
    """Depth as colour: near is warm, far is cool, no reading is black."""
    t = np.clip((depth_mm.astype(float) - 200) / 600, 0, 1)[..., None]
    near, far = np.array([255, 196, 64]), np.array([40, 60, 160])
    picture = (near * (1 - t) + far * t).astype(np.uint8)
    picture[depth_mm == 0] = 0
    return picture


def copy_field(lines: list[dict]) -> None:
    out = WEB / "field"
    out.mkdir(parents=True, exist_ok=True)
    for line in lines:
        pick = line["pick"]
        shutil.copy(reproduce_scene.FIELD / "images" / f"{pick}_rgb.png", out / f"{pick}_rgb.png")
        depth = np.asarray(pil_image.open(reproduce_scene.FIELD / "images" / f"{pick}_depth.png"))
        pil_image.fromarray(depth_picture(depth)).save(out / f"{pick}_depth.png")


# ---- 2 and 3. the simulation -------------------------------------------------------


def to_pixels(berry, camera: dict) -> list[float]:
    """The box a berry fills in the robot's image."""
    x, z, y = berry.center - reproduce_scene.CAMERA_POSITION  # world (x, y, z) to camera (x, z, -y)
    y = -y
    u, v = camera["fx"] * x / z + camera["cx"], camera["fy"] * y / z + camera["cy"]
    half_w = camera["fx"] * berry.radius / z
    half_h = 1.4 * half_w
    return [round(u - half_w, 1), round(v - half_h, 1), round(u + half_w, 1), round(v + half_h, 1)]


def save_video(frames: list[np.ndarray], path: pathlib.Path) -> None:
    """H.264 at the simulation's own pace; the last frame is held for a second."""
    frames = frames + [frames[-1]] * reproduce_scene.FILM_FPS
    h, w = frames[0].shape[:2]
    writer = imageio_ffmpeg.write_frames(str(path), (w, h), fps=reproduce_scene.FILM_FPS, codec="libx264",
                                         pix_fmt_out="yuv420p", output_params=["-crf", "26"])
    writer.send(None)
    for frame in frames:
        writer.send(np.ascontiguousarray(frame))
    writer.close()


def run_all(lines: list[dict], camera: dict, film_to: pathlib.Path) -> list[dict]:
    """Every attempt in the simulator with whatever robot_controller is loaded; the failed one filmed."""
    results = []
    for line in lines:
        film = line["pick"] == FAILED_PICK
        result = reproduce_scene.reproduce(line, camera, film=film)
        if film:
            for view, frames in result.pop("frames").items():  # before.mp4, before-side.mp4, before-top.mp4
                name = film_to.stem if view == "angled" else f"{film_to.stem}-{view}"
                save_video(frames, film_to.with_name(name + film_to.suffix))
            result.pop("model"), result.pop("found"), result.pop("target")
        results.append({**result, "field": line["outcome"]})
        log(f"  {line['pick']}: field {line['outcome']}, simulation {result['outcome']}")
    return results


def describe_failed(line: dict, camera: dict) -> list[dict]:
    """The berries found in the failed attempt's image, and the scene seen from the robot's camera."""
    result = reproduce_scene.reproduce(line, camera, film=True)
    model, found, target = result["model"], result["found"], result["target"]
    data = mujoco.MjData(model)
    target_index = next(i for i, berry in enumerate(found) if berry is target)
    data.qpos[:] = reproduce_scene.Run(model, target_index).data.qpos
    mujoco.mj_forward(model, data)
    with mujoco.Renderer(model, 640, 640) as renderer:
        renderer.update_scene(data, "robot")
        pil_image.fromarray(renderer.render()).save(WEB / "sim-view.png")
    # The page draws YOLO's own boxes: each berry gets the box nearest to where it sits in the image.
    rgb = np.asarray(pil_image.open(ROOT / "data" / "field" / "images" / f"{line['pick']}_rgb.png").convert("RGB"))
    boxes = reproduce_scene.detect(rgb)
    described = []
    for b in found:
        u0, v0, u1, v1 = to_pixels(b, camera)
        box, _, confidence = min(boxes, key=lambda d: np.hypot((d[0][0] + d[0][2] - u0 - u1) / 2,
                                                                (d[0][1] + d[0][3] - v0 - v1) / 2))
        described.append({"ripe": b.ripe, "target": b is target, "center": [round(float(v), 3) for v in b.center],
                          "radius_mm": round(b.radius * 1000, 1), "box": [round(float(v), 1) for v in box],
                          "confidence": round(confidence, 2)})
    return described


# ---- 4. the agent -----------------------------------------------------------------


def reset_work() -> None:
    """A fresh copy of the code for the agent, and a snapshot of it that the agent cannot touch."""
    for folder in (WORK, ORIGINAL):
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(HERE, folder / "src" / "harvest",
                        ignore=shutil.ignore_patterns("__pycache__", "bake_demo.py"))
    (WORK / "data").symlink_to(ROOT / "data")
    (WORK / "models").symlink_to(ROOT / "models")
    check = WORK / "check.sh"
    check.write_text(CHECK_SH.format(root=ROOT))
    check.chmod(0o755)


def run_agent(line: dict) -> dict:
    """Claude Code on a fresh copy, headless; its transcript kept for the page."""
    reset_work()
    prompt = PROMPT.format(pick=line["pick"], outcome=line["outcome"], force=line["peak_force_n"],
                           cycle=line["cycle_s"])
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--max-turns", "60",
           "--setting-sources", "project",  # the presenter's own settings are not the agent's business
           "--append-system-prompt", UNATTENDED,
           "--allowedTools", "Read", "Edit", "Grep", "Glob", "Bash(./check.sh)"]
    log(f"agent: {MODEL} in {WORK}")
    started = time.time()
    clock = lambda: round(time.time() - started)  # noqa: E731
    transcript, checks, result, commands = [], [], {}, {}
    with open(WORK.parent / "agent.stderr.log", "w") as errors:
        proc = subprocess.Popen(cmd, cwd=WORK, stdout=subprocess.PIPE, stderr=errors, text=True)
        for raw in proc.stdout:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if time.time() - started > AGENT_TIMEOUT_S:
                proc.kill()
            message = event.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            content = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []
            if event.get("type") == "assistant":
                for block in content:
                    if block.get("type") == "text" and block["text"].strip():
                        transcript.append({"t": clock(), "say": block["text"].strip()})
                    elif block.get("type") == "tool_use":
                        args = block.get("input", {})
                        what = args.get("file_path") or args.get("command") or args.get("pattern") or ""
                        commands[block["id"]] = what
                        transcript.append({"t": clock(), "tool": block["name"], "what": pathlib.Path(what).name})
                        log(f"  {clock():4d}s {block['name']} {what[:60]}")
            elif event.get("type") == "user":
                for block in content:
                    if block.get("type") == "tool_result":
                        if commands.get(block.get("tool_use_id"), "").startswith("./check.sh"):
                            text = json.dumps(block.get("content"))
                            checks.append({"t": clock(), "passed": "10 of 10 attempts picked" in text})
            elif event.get("type") == "result":
                result = {"text": event.get("result") or "", "turns": event.get("num_turns"),
                          "seconds": round((event.get("duration_ms") or 0) / 1000),
                          "cost_usd": event.get("total_cost_usd")}
        proc.wait()
    agent = {"model": MODEL, "prompt": prompt, "transcript": transcript, "checks": checks, **result,
             "exit": proc.returncode}
    (WORK.parent / "agent.json").write_text(json.dumps(agent, indent=1))
    log(f"agent finished: exit {proc.returncode}, {result.get('turns')} turns, {result.get('seconds')} s")
    return agent


def code_diff() -> list[dict]:
    """What the agent changed, file by file; anything but robot_controller.py is flagged.

    The agent's copy is compared with the snapshot taken before it started, not
    with src/harvest/ now, which may have moved on since the agent ran.
    """
    before, after = ORIGINAL / "src" / "harvest", WORK / "src" / "harvest"
    names = sorted({p.name for p in before.glob("*.py")} | {p.name for p in after.glob("*.py")})
    files = []
    for name in names:
        old, new = before / name, after / name
        a = old.read_text().splitlines(keepends=True) if old.exists() else []
        b = new.read_text().splitlines(keepends=True) if new.exists() else []
        if a != b:
            marks = [line[:2] for line in difflib.ndiff(a, b)]
            files.append({"path": f"src/harvest/{name}", "protected": name != "robot_controller.py",
                          "diff": "".join(difflib.unified_diff(a, b, f"a/src/harvest/{name}", f"b/src/harvest/{name}")),
                          "added": marks.count("+ "), "removed": marks.count("- ")})
    return files


def pull_request(text: str) -> dict:
    title, body, explanation = "", text, text
    if "PR-TITLE:" in text:
        explanation, after = text.split("PR-TITLE:", 1)
        title = after.split("\n", 1)[0].strip()
        body = after.split("PR-BODY:", 1)[1] if "PR-BODY:" in after else after.split("\n", 1)[-1]
    return {"title": title, "body": body.strip(), "explanation": explanation.strip(),
            "branch": "fix/approach-around-front-berry", "base": "main", "reviewer": "klahisaac"}


def load_agent_controller() -> None:
    """Make the simulator use the agent's robot_controller.py instead of the original."""
    spec = importlib.util.spec_from_file_location("agent_robot_controller",
                                                  WORK / "src" / "harvest" / "robot_controller.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reproduce_scene.robot_controller = module


# ---- bake -------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-agent", action="store_true", help="reuse the agent's last copy and transcript")
    args = parser.parse_args()

    WEB.mkdir(parents=True, exist_ok=True)
    camera = json.loads((ROOT / "data" / "camera.json").read_text())
    lines = [json.loads(s) for s in (reproduce_scene.FIELD / "harvest_log.jsonl").read_text().splitlines()]
    failed = next(line for line in lines if line["pick"] == FAILED_PICK)

    log("1. field data")
    copy_field(lines)
    log("2. the failed attempt as a simulation")
    found = describe_failed(failed, camera)
    log("3. every attempt with the robot code as it is")
    before = run_all(lines, camera, WEB / "before.mp4")

    log("4. the agent")
    agent = run_agent(failed) if not args.no_agent else json.loads((WORK.parent / "agent.json").read_text())
    if "english" in json.dumps([agent.get("text"), agent.get("transcript")]).lower():
        log("warning: the agent's replies mention English; check them before publishing")
    diff = code_diff()
    log("5. every attempt with the agent's code")
    load_agent_controller()
    after = run_all(lines, camera, WEB / "after.mp4")

    claude = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.split()
    demo = {
        "meta": {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                 "versions": {"mujoco": mujoco.__version__, "python": platform.python_version(),
                              "claude_code": claude[0] if claude else ""}},
        "logs": lines, "failed_pick": FAILED_PICK, "camera": camera, "found": found,
        "before": before, "agent": agent, "diff": diff, "after": after,
        "pr": pull_request(agent.get("text", "")),
        "rules": {"force_limit_n": reproduce_scene.FORCE_LIMIT, "reach_mm": reproduce_scene.REACH_TOLERANCE * 1000,
                  "tool_speed_m_s": reproduce_scene.TOOL_SPEED},
    }
    (WEB / "data.js").write_text("window.DEMO = " + json.dumps(demo, indent=1) + ";\n")
    picked = sum(r["outcome"] == "picked" for r in after)
    log(f"done: {picked} of {len(after)} picked with the agent's code; wrote {WEB / 'data.js'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
