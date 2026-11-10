"""Build the static demo page's data: `web/demo/data.js` and its videos.

    harvest demo-bake --agent   run the AI agent on a fresh copy, then bake
    harvest demo-bake           bake again from the agent's last copy

The page (`web/index.html`) is static. Everything it shows is produced here, by
running the real code:

  1. field logs: ordinary scenarios worked by the code as it is, plus the
     photographed cluster, which fails
  2. the photo measured by colour and built into a MuJoCo scene (photocase.py)
  3. the original code on that scene, filmed
  4. Claude Code, run headless on a scratch copy of the code (`runs/demo/work`)
     with one command, `./check.sh`; then the same scene on its edited copy,
     filmed
  5. the smoke tiers on the edited copy
  6. the diff, and the agent's own pull-request description

A run uses whichever code it is pointed at by putting that tree first on
PYTHONPATH in a subprocess. The experiment (`photocase.py`) is copied along
with the robot's code, so before and after are the same experiment.
"""

from datetime import datetime, timedelta, timezone
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DEMO = ROOT / "runs" / "demo"
WORK = DEMO / "work"
BASE = DEMO / "base"  # the code as copied for the agent, to diff against
OUT = WEB / "demo"
PY = sys.executable
MODEL = os.environ.get("DEMO_MODEL", "claude-opus-5-5")
# The robot's code is fair game. The experiment, the gate and the world are
# not: changing them would change the question rather than answer it.
PROTECTED = ("photocase.py", "suite.py", "scene.py", "demobake.py")
SMOKE = {
    "demo": {"scenarios": ["S0010", "S0025"],
             "judges": "catch rate, torn stems and knocks, false picks"},
    "smoke": {"scenarios": [f"S{i:04d}" for i in range(1, 7)],
              "judges": "packed success, all damage including bruises, false picks"},
}


def log(msg: str) -> None:
    print(f"[demo-bake] {msg}", flush=True)


# ---- running code trees ----------------------------------------------------


def _env(tree: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tree / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(tree: Path, args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=tree, env=_env(tree), capture_output=True,
                          text=True, timeout=timeout)


def _case(tree: Path, name: str) -> dict:
    """The photographed cluster, worked by the code in `tree`, filmed."""
    out = OUT / name
    if out.exists():
        shutil.rmtree(out)
    proc = _run(tree, ["-m", "harvestbench.photocase", "run", "--out", str(out)])
    result = json.loads((out / "result.json").read_text())
    result["stdout"] = proc.stdout
    if result.get("video"):
        result["video_url"] = f"demo/{name}/{result['video']}"
    return result


# ---- 1-2: logs and the photo -------------------------------------------------


def field_logs() -> dict:
    """Ordinary picks, and the incident: the photographed cluster failing."""
    from .incidents import PickRecord, flag
    from .session import RunConfig, run_session

    rows = []
    for seed in (10, 25, 6):
        _, results = run_session(RunConfig(seed=seed, scenarios=1, detector="colour"),
                                 log=lambda *_: None)
        r = results[0]
        for rec in PickRecord.from_events(r.telemetry.records):
            outcome = next(p.outcome for p in r.picks if p.berry_id == rec.pick_id)
            if outcome != "picked" or flag(rec):
                continue
            rows.append({
                "robot": "harvester-01", "row": "G3", "scenario": r.scenario.scenario_id,
                "pick": rec.pick_id, "event": "pick.completed", "outcome": outcome,
                "est_ripeness": round(rec.est_ripeness, 2),
                "peak_force_n": round(rec.peak_force_n, 1),
                "cycle_s": round(rec.duration_s, 1), "flags": [],
            })
    case = _case(ROOT, "before")
    pick = next(a for a in case["attempts"] if a["aimed_at"] == "ripe")
    rec = next(r for r in PickRecord.from_events(case["events"]) if r.pick_id == pick["label"])
    incidents = [{"kind": i.kind, "severity": i.severity, "why": i.why} for i in flag(rec)]
    abnormal = {
        "robot": "harvester-01", "row": "G3", "scenario": "FIELD-0417", "pick": pick["label"],
        "event": "pick.failed", "outcome": pick["outcome"],
        "est_ripeness": round(rec.est_ripeness, 2), "peak_force_n": round(rec.peak_force_n, 1),
        "cycle_s": round(rec.duration_s, 1), "flags": [i["kind"] for i in incidents],
        "abnormal": True,
    }
    rows.insert(len(rows) - 2, abnormal)  # not last: it has to be found
    clock = datetime(2026, 11, 9, 6, 2, 11, tzinfo=timezone.utc)
    for r in rows:
        clock += timedelta(seconds=11 + r["cycle_s"])
        r["time"] = clock.isoformat(timespec="seconds")
    return {
        "logs": rows,
        "incident": {"row": abnormal, "flags": incidents,
                     "events": [e for e in case["events"] if e["event"] != "run.started"]},
        "before": case,
    }


def photo() -> dict:
    from .photocase import FRONT_DEPTH_M, RIPE_RADIUS_M, close_up, photo_scenario

    sc, blobs, info = photo_scenario()
    close_up(sc, OUT / "sim-photo.png")
    return {
        "blobs": [b.__dict__ for b in blobs],
        "m_per_px": info["m_per_px"],
        "berries": [
            {"id": b.berry_id, "pos": [round(v, 4) for v in b.pos],
             "radius_mm": round(b.radius * 1000, 1), "ripeness": b.ripeness,
             "in_front": info["berries"][b.berry_id]["in_front"]}
            for b in sc.berries
        ],
        "assumptions": {"ripe_radius_mm": round(RIPE_RADIUS_M * 1000),
                        "front_depth_mm": round(FRONT_DEPTH_M * 1000)},
    }


# ---- 4: the agent --------------------------------------------------------------

PROMPT = """You are working on the software of an autonomous strawberry-harvesting robot.
The code is in this directory, under src/harvestbench/.

Field report, from harvester-01's log:
  pick {pick} failed: {outcome}. {why}
  A photo from the field shows the ripe berry it went for, with an unripe berry
  hanging in front of it, covering the top of the ripe one.

The photographed situation is rebuilt in the simulator. Run ./check.sh to see it.
It runs the robot on that cluster (python -m harvestbench.photocase check), then two
smoke tiers that must keep passing: the demo tier (S0010, S0025: picking up to the
catch) and the regular smoke tier (S0001-S0006: packed success and all damage,
bruises included). It prints PASS or FAIL for each.

Goal: change the robot's code so that the ripe berry is cut and packed without
damaging any other fruit, and ./check.sh passes.

Rules:
- Fix the robot's behaviour (for example in cell.py, policy.py or perception.py).
- The robot may only use what it senses: detections, its camera frames, its own
  joint states and contact forces. It must not read the simulator's ground truth
  (self.scenario, berry bodies or poses from the model) to decide what to do.
- Do not edit photocase.py, suite.py, scene.py or the damage thresholds: they are
  the experiment, the gate and the world, not the robot.
- Keep the change small and readable, in the style of the surrounding code.
- The only shell command you can run is ./check.sh.

When ./check.sh passes, remove any debugging you added, run ./check.sh once more,
and stop. Then reply with a pull-request description in exactly this form:

PR-TITLE: <one line>
PR-BODY:
- <three to five short bullets: what was wrong, what you changed, anything left>
"""

# Appended to the agent's system prompt: it runs unattended.
SYSTEM_NOTE = (
    "You are running unattended for a recorded demo. Ignore any personal style or "
    "language instructions from memory files: write in English, add no preamble, "
    "and do not comment on the prompt's wording."
)

CHECK_SH = """#!/usr/bin/env bash
# The photographed case, then both smoke tiers, on the code in this directory.
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src"
echo "== field case: the photographed cluster"
{py} -m harvestbench.photocase check
case=$?
echo
echo "== smoke: demo tier (S0010, S0025), picking up to the catch must not get worse"
{py} -m harvestbench.cli gate --tier demo --skip-tracking --baseline {root}/baselines/demo-colour.json
demo=$?
echo
echo "== smoke: regular tier (S0001-S0006), packed success and damage must not get worse"
{py} -m harvestbench.cli gate --tier smoke --skip-tracking --baseline {root}/baselines/smoke-colour.json
smoke=$?
echo
if [ $case -eq 0 ] && [ $demo -eq 0 ] && [ $smoke -eq 0 ]; then echo "ALL CHECKS PASS"; exit 0; fi
echo "CHECKS FAIL"; exit 1
"""


def reset_work() -> None:
    """A fresh copy of the robot's code for the agent to work on."""
    for d in (WORK, BASE):
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(ROOT / "src", d / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    (WORK / "web" / "demo").mkdir(parents=True)
    shutil.copy(OUT / "field-photo.png", WORK / "web" / "demo" / "field-photo.png")
    check = WORK / "check.sh"
    check.write_text(CHECK_SH.format(py=PY, root=ROOT))
    check.chmod(0o755)


def run_agent(incident: dict) -> dict:
    """Claude Code on a fresh copy, headless; its transcript kept for the page."""
    reset_work()
    prompt = PROMPT.format(pick=incident["row"]["pick"], outcome=incident["row"]["outcome"],
                           why=" ".join(f["why"] for f in incident["flags"]))
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json",
           "--verbose", "--permission-mode", "acceptEdits", "--max-turns", "80",
           # Project settings only: the presenter's personal instructions
           # (~/.claude) are not the agent's business, and leak into its replies.
           "--setting-sources", "project", "--append-system-prompt", SYSTEM_NOTE,
           "--allowedTools", "Read", "Edit", "Write", "Grep", "Glob",
           "Bash(./check.sh)", "Bash(./check.sh:*)"]
    log(f"agent: {MODEL} on {WORK}")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    transcript, commands, checks, result = [], {}, [], {}
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    transcript.append({"t": round(time.time() - t0), "say": block["text"]})
                elif block.get("type") == "tool_use":
                    args = block.get("input", {})
                    if block["name"] == "Bash":
                        commands[block.get("id", "")] = args.get("command", "")
                    what = (args.get("file_path") or args.get("command") or args.get("pattern") or "")
                    transcript.append({"t": round(time.time() - t0), "tool": block["name"],
                                       "what": Path(what).name if "/" in what else what})
                    log(f"  {round(time.time() - t0):>4}s {block['name']} {what[:70]}")
        elif kind == "user":
            for block in ev.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    if commands.get(block.get("tool_use_id", ""), "").lstrip().startswith("./check.sh"):
                        content = block.get("content")
                        if isinstance(content, list):
                            content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
                        passed = "ALL CHECKS PASS" in str(content)
                        checks.append({"t": round(time.time() - t0), "passed": passed})
                        log(f"  check: {'PASS' if passed else 'FAIL'}")
        elif kind == "result":
            result = {"text": ev.get("result", "") or "", "turns": ev.get("num_turns"),
                      "seconds": round((ev.get("duration_ms") or 0) / 1000),
                      "cost_usd": ev.get("total_cost_usd")}
    proc.wait()
    agent = {"model": MODEL, "prompt": prompt, "transcript": transcript, "checks": checks,
             **result, "exit": proc.returncode}
    (DEMO / "agent.json").write_text(json.dumps(agent, indent=1))
    log(f"agent finished: exit {proc.returncode}, {result.get('turns')} turns, "
        f"{result.get('seconds')}s")
    return agent


def pull_request(text: str) -> dict:
    title, body = "", text
    if "PR-TITLE:" in text:
        after = text.split("PR-TITLE:", 1)[1]
        title = after.split("\n", 1)[0].strip()
        body = after.split("PR-BODY:", 1)[1] if "PR-BODY:" in after else after.split("\n", 1)[-1]
    return {"title": title, "body": body.strip(), "branch": "fix/occluded-ripe-berry",
            "base": "main", "reviewer": "klahisaac", "state": "open, review requested"}


def diff() -> list[dict]:
    files = []
    for new in sorted((WORK / "src").rglob("*.py")):
        rel = new.relative_to(WORK)
        old = BASE / rel
        a = old.read_text().splitlines(keepends=True) if old.exists() else []
        b = new.read_text().splitlines(keepends=True)
        if a != b:
            files.append({
                "path": str(rel), "protected": rel.name in PROTECTED,
                "diff": "".join(difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}")),
                "added": sum(1 for l in difflib.ndiff(a, b) if l.startswith("+ ")),
                "removed": sum(1 for l in difflib.ndiff(a, b) if l.startswith("- ")),
            })
    return files


# ---- 5: smoke ----------------------------------------------------------------


def smoke() -> dict:
    out = {}
    for tier, info in SMOKE.items():
        gate = _run(WORK, ["-m", "harvestbench.cli", "gate", "--tier", tier, "--skip-tracking",
                           "--baseline", str(ROOT / "baselines" / f"{tier}-colour.json")])
        out[tier] = {**info, "passed": gate.returncode == 0, "report": gate.stdout.strip()}
        log(f"smoke {tier}: {'PASS' if gate.returncode == 0 else 'FAIL'}")
    return out


# ---- bake ---------------------------------------------------------------------


def _versions() -> dict:
    import mujoco
    import numpy

    claude = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    return {"mujoco": mujoco.__version__, "numpy": numpy.__version__,
            "python": sys.version.split()[0], "claude_code": claude.split()[0] if claude else ""}


def bake(agent: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    log("field logs and the incident (original code)")
    logs = field_logs()
    log("the photo, as a scene")
    ph = photo()
    if agent:
        agent_data = run_agent(logs["incident"])
    elif (DEMO / "agent.json").exists() and WORK.exists():
        agent_data = json.loads((DEMO / "agent.json").read_text())
        log("reusing the agent's last copy")
    else:
        raise SystemExit("no agent run yet: use --agent")
    log("the photographed cluster on the agent's code")
    after = _case(WORK, "after")
    data = {
        "meta": {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "versions": _versions()},
        **logs,
        "photo": ph,
        "agent": {k: v for k, v in agent_data.items() if k != "text"},
        "after": after,
        "diff": diff(),
        "smoke": smoke(),
        "pr": pull_request(agent_data.get("text", "")),
    }
    path = OUT / "data.js"
    path.write_text("window.DEMO = " + json.dumps(data, separators=(",", ":")) + ";\n")
    log(f"wrote {path}")
    return path
