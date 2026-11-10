"""The loop: observe, choose, pick, score.

Shaped after lab-robot's `run_campaign`. A config dataclass, an injectable
logger so a large suite can run quietly, an optional observer, and
`out_dir=None` to keep a run entirely in memory — which is what
makes running a few hundred scenarios cheap.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

import numpy as np

from . import metrics, scene
from .camera import Intrinsics, camera_pose
from .cell import MuJoCoCell, PickResult, SensorConfig
from .perception import ColorThresholdDetector
from .policy import BaselinePolicy
from .scenario import Scenario, generate
from .telemetry import Telemetry


@dataclass
class RunConfig:
    seed: int = 0
    scenarios: int = 1
    n_berries: int = 6
    policy: str = "baseline"
    detector: str | None = None
    sensor: SensorConfig = field(default_factory=SensorConfig)
    frame_hz: float = 0.0  # >0 records the arm's trajectory
    out_dir: Path | None = None  # None: nothing written, nothing kept on disk


@dataclass
class ScenarioResult:
    scenario: Scenario
    picks: list[PickResult]
    detections: list
    matched: dict
    occlusion: dict  # measured from pixels, not the scenario's nominal value
    survey_frame: object  # the picture perception read
    intrinsics: object
    cam_pos: object
    cam_mat: object
    targeted: list[str]
    skipped: list[str]
    missed_undetected: list[str]
    duration_s: float
    telemetry: Telemetry
    frames: list[dict]
    mjcf: str


POLICIES = {"baseline": BaselinePolicy}
DETECTORS = {"colour": ColorThresholdDetector}

# How close a detection has to land to count as the same berry (metres).
MATCH_RADIUS_M = 0.06


def match_detections(scenario: Scenario, detections: list) -> dict[str, str | None]:
    """Nearest-berry assignment, greedy and one to one.

    Maps each detection's label to a real berry id, or None when it landed on
    nothing — a false positive. This is evaluation machinery; nothing the robot
    does is allowed to use it.
    """
    pairs = sorted(
        (
            (float(np.linalg.norm(np.array(d.pos) - np.array(b.pos))), d.berry_id, b.berry_id)
            for d in detections
            for b in scenario.berries
        ),
        key=lambda t: t[0],
    )
    out: dict[str, str | None] = {d.berry_id: None for d in detections}
    taken: set[str] = set()
    for dist, det_id, berry_id in pairs:
        if dist > MATCH_RADIUS_M or berry_id in taken or out[det_id] is not None:
            continue
        out[det_id] = berry_id
        taken.add(berry_id)
    return out


def run_scenario(scenario: Scenario, cfg: RunConfig, observer=None) -> ScenarioResult:
    def notify(name, **kw):
        if observer is not None and hasattr(observer, name):
            getattr(observer, name)(**kw)

    policy = POLICIES[cfg.policy]()
    cell = MuJoCoCell(
        scenario,
        seed=cfg.seed,
        sensor=cfg.sensor,
        frame_hz=cfg.frame_hz,
        detector=DETECTORS[cfg.detector]() if cfg.detector else None,
    )
    t0 = cell.time

    # Measured once, before the arm moves, and from the survey viewpoint with
    # the arm left out of the render. This is what the metric buckets use; the
    # scenario's own `occlusion` only ever decided how big a leaf to make.
    occlusion = cell.occlusion

    detections = cell.observe()
    cam_pos, cam_mat = camera_pose(cell.model, cell.data, scene.SURVEY_CAM)
    # A detection is a position, not an identity. Match each one to the nearest
    # real berry so the scenario's bookkeeping stays in truth ids whichever
    # perception path produced it.
    matched = match_detections(scenario, detections)
    seen = {bid for bid in matched.values() if bid}
    targets = policy.choose(detections)
    chosen = {matched.get(d.berry_id) for d in targets}
    notify(
        "on_observe",
        scenario=scenario,
        detections=detections,
        matched=matched,
        occlusion=occlusion,
        survey_frame=cell.survey_frame,
        intrinsics=Intrinsics.of(cell.model, scene.SURVEY_CAM, *cell.camera_size),
        cam_pos=cam_pos,
        cam_mat=cam_mat,
        targets=targets,
        policy=policy,
    )

    picks = []
    for target in targets:
        result = cell.pick(target)
        picks.append(result)
        notify("on_pick", scenario=scenario, target=target, result=result, cell=cell)

    return ScenarioResult(
        scenario=scenario,
        picks=picks,
        detections=detections,
        matched=matched,
        occlusion=occlusion,
        survey_frame=cell.survey_frame,
        intrinsics=Intrinsics.of(cell.model, scene.SURVEY_CAM, *cell.camera_size),
        cam_pos=cam_pos,
        cam_mat=cam_mat,
        targeted=[matched[d.berry_id] for d in targets if matched.get(d.berry_id)],
        skipped=[
            bid
            for d in detections
            if (bid := matched.get(d.berry_id)) and bid not in chosen
        ],
        missed_undetected=[b.berry_id for b in scenario.berries if b.berry_id not in seen],
        duration_s=cell.time - t0,
        telemetry=cell.telemetry,
        frames=cell.frames,
        mjcf=cell.mjcf,
    )


def write_survey(d: Path, r: ScenarioResult) -> None:
    """The RGB-D frame perception planned from, and the camera that took it.

    A field machine keeps this with its log. It is what lets a failure be
    rebuilt offline: berries from what perception reported, everything else —
    leaves above all — from the picture and its depth.
    """
    from .imaging import write_png

    if r.survey_frame is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    write_png(d / "survey.png", r.survey_frame.rgb)
    np.save(d / "survey_depth.npy", r.survey_frame.depth.astype(np.float32))
    intr = r.intrinsics
    (d / "camera.json").write_text(json.dumps({
        "width": intr.width, "height": intr.height,
        "fx": intr.fx, "fy": intr.fy, "cx": intr.cx, "cy": intr.cy,
        "pos": [float(v) for v in r.cam_pos],
        "mat": [float(v) for v in np.asarray(r.cam_mat).ravel()],
    }, indent=2))


def run_session(cfg: RunConfig, log=print, observer=None) -> tuple[metrics.Metrics, list[ScenarioResult]]:
    """Run cfg.scenarios scenarios and score them together."""
    results = []
    for i in range(cfg.scenarios):
        scenario = generate(
            seed=cfg.seed + i, n_berries=cfg.n_berries, scenario_id=f"S{cfg.seed + i:04d}"
        )
        r = run_scenario(scenario, cfg, observer=observer)
        results.append(r)
        picked = sum(1 for p in r.picks if p.caught)
        log(
            f"{scenario.scenario_id}  ripe {len(scenario.pickable)}/{len(scenario.berries)}  "
            f"targeted {len(r.targeted)}  picked {picked}  {r.duration_s:.1f}s"
        )
        if cfg.out_dir:
            d = cfg.out_dir / scenario.scenario_id
            r.telemetry.write_jsonl(d / "telemetry.jsonl")
            (d / "scene.xml").write_text(r.mjcf)
            write_survey(d, r)

    m = metrics.score(results)
    if cfg.out_dir:
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        (cfg.out_dir / "metrics.json").write_text(json.dumps(m.as_dict(), indent=2))
        (cfg.out_dir / "config.json").write_text(
            json.dumps({k: str(v) for k, v in asdict(cfg).items()}, indent=2)
        )
    return m, results
