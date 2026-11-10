"""The scenario suite and the gate that reads it.

Two tiers, because the posting names simulation and smoke testing as separate
steps and because a bench that takes twenty minutes to answer stops being used:

  * **smoke** — a handful of scenarios, seconds, on every commit.
  * **full**  — the whole corpus across every core, on a pull request.

The bench is deterministic — same seeds, fixed timestep, pinned thresholds — so
a diff against a recorded baseline is exact. There is no statistical tolerance
to argue about and no flaky scenario to re-run: if a number moved, something in
the code moved it. That is the whole reason the seeds are pinned.
"""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path

from . import metrics
from .session import RunConfig, run_scenario
from .scenario import generate

TIERS = {"smoke": 6, "full": 40, "demo": 2}

# Tiers made of chosen scenarios rather than the first N seeds. The demo tier is
# the two scenarios where every ripe berry is caught with nothing torn or
# knocked, on both perception paths: a change that breaks either is visible at
# once, and a clean pass is unambiguous.
PINNED = {"demo": (10, 25)}

# What a gate failure is. Success must not fall and damage must not rise; both
# are compared exactly, because the runs are reproducible.
RULES = (
    ("success_rate", "higher"),
    ("damage_events", "lower"),
    ("false_picks", "lower"),
)

# The demo tier judges picking only — up to the catch. The carry and the drop
# still run, so the scenario plays out as it would, but spills and bruises are
# recorded rather than judged: the demo is about getting fruit off the plant.
PICK_RULES = (
    ("catch_rate", "higher"),
    ("pick_damage", "lower"),
    ("false_picks", "lower"),
)
TIER_RULES = {"demo": PICK_RULES}


def rules_for(tier: str) -> tuple:
    return TIER_RULES.get(tier, RULES)


@dataclass
class ScenarioRow:
    """One scenario's result, small enough to store and diff."""

    id: str
    ripe_total: int
    picked_ripe: int
    damage_events: int
    false_picks: int
    unreachable: int
    attempts: int
    # Added with the place step. Defaults keep older baselines loadable.
    spilled: int = 0
    bruised: int = 0
    caught_ripe: int = 0
    pick_damage: int = 0

    @property
    def key(self) -> tuple:
        return (self.picked_ripe, self.damage_events, self.false_picks, self.unreachable,
                self.spilled, self.bruised)

    @property
    def pick_key(self) -> tuple:
        """The part of the result decided by the time the berry is caught."""
        return (self.caught_ripe, self.pick_damage, self.false_picks, self.unreachable)


def _one(args) -> tuple[ScenarioRow, dict]:
    """Worker body. Must be importable, so it lives at module level."""
    seed, cfg = args
    scenario = generate(seed=seed, n_berries=cfg.n_berries, scenario_id=f"S{seed:04d}")
    r = run_scenario(scenario, cfg)
    m = metrics.score([r])
    return (
        ScenarioRow(
            id=scenario.scenario_id,
            ripe_total=m.ripe_total,
            picked_ripe=m.picked_ripe,
            damage_events=m.damage_events,
            false_picks=m.false_picks,
            unreachable=m.unreachable,
            attempts=m.attempts,
            spilled=m.spilled,
            bruised=m.bruised,
            caught_ripe=m.caught_ripe,
            pick_damage=m.pick_damage,
        ),
        m.as_dict(),
    )


@dataclass
class SuiteResult:
    tier: str
    detector: str | None
    policy: str
    rows: list[ScenarioRow]
    totals: dict

    def as_dict(self) -> dict:
        return {
            "tier": self.tier,
            "detector": self.detector,
            "policy": self.policy,
            "totals": self.totals,
            "rows": [asdict(r) for r in self.rows],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SuiteResult":
        return cls(
            tier=d["tier"], detector=d.get("detector"), policy=d["policy"],
            totals=d["totals"], rows=[ScenarioRow(**r) for r in d["rows"]],
        )

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n")
        return path


def run_suite(
    tier: str = "full",
    seed: int = 1,
    n_berries: int = 6,
    policy: str = "baseline",
    detector: str | None = "colour",
    workers: int | None = None,
    log=print,
) -> SuiteResult:
    """Every scenario in the tier, in parallel, scored together."""
    cfg = RunConfig(
        seed=seed, scenarios=1, n_berries=n_berries, policy=policy, detector=detector
    )
    scenario_seeds = PINNED.get(tier) or [seed + i for i in range(TIERS[tier])]
    jobs = [(s, cfg) for s in scenario_seeds]
    workers = workers or min(len(jobs), max(1, (os.cpu_count() or 4) // 2))

    # Spawn, never fork. A parent that has rendered owns an OpenGL context, and
    # the software rasterizer behind it runs its own threads; a forked child
    # inherits the locks without the threads and hangs on its first frame.
    ctx = multiprocessing.get_context("spawn")
    rows, totals = [], []
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        for row, per in pool.map(_one, jobs):
            rows.append(row)
            totals.append(per)
            if rules_for(tier) is PICK_RULES:
                log(
                    f"{row.id}  caught {row.caught_ripe}/{row.ripe_total}  "
                    f"pick damage {row.pick_damage}  attempts {row.attempts}"
                )
            else:
                log(
                    f"{row.id}  picked {row.picked_ripe}/{row.ripe_total}  "
                    f"damage {row.damage_events}  attempts {row.attempts}"
                )

    rows.sort(key=lambda r: r.id)
    agg = _aggregate(rows)
    return SuiteResult(tier=tier, detector=detector, policy=policy, rows=rows, totals=agg)


def _aggregate(rows: list[ScenarioRow]) -> dict:
    ripe = sum(r.ripe_total for r in rows)
    picked = sum(r.picked_ripe for r in rows)
    return {
        "scenarios": len(rows),
        "ripe_total": ripe,
        "picked_ripe": picked,
        "success_rate": round(picked / ripe, 4) if ripe else 0.0,
        "catch_rate": (
            round(sum(r.caught_ripe for r in rows) / ripe, 4) if ripe else 0.0
        ),
        "pick_damage": sum(r.pick_damage for r in rows),
        "damage_events": sum(r.damage_events for r in rows),
        "false_picks": sum(r.false_picks for r in rows),
        "unreachable": sum(r.unreachable for r in rows),
        "attempts": sum(r.attempts for r in rows),
        "spilled": sum(r.spilled for r in rows),
        "bruised": sum(r.bruised for r in rows),
    }


# ---- the gate ------------------------------------------------------------


@dataclass
class Verdict:
    passed: bool
    failures: list[str] = field(default_factory=list)
    improved: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["PASS" if self.passed else "FAIL"]
        for name, items in (
            ("regressed", self.failures),
            ("improved", self.improved),
            ("scenarios changed", self.changed),
            ("not in the baseline", self.missing),
        ):
            if items:
                lines.append(f"\n{name}:")
                lines += [f"  {i}" for i in items]
        return "\n".join(lines)


def compare(current: SuiteResult, baseline: SuiteResult) -> Verdict:
    """Exact diff against a recorded run.

    A change that lifts the average while introducing one new damage case is
    the interesting case, and it is why the per-scenario breakdown is here and
    not just the totals.
    """
    v = Verdict(passed=True)
    if (current.tier, current.detector, current.policy) != (
        baseline.tier, baseline.detector, baseline.policy
    ):
        v.passed = False
        v.failures.append(
            f"baseline is {baseline.tier}/{baseline.policy}/{baseline.detector}, "
            f"this run is {current.tier}/{current.policy}/{current.detector}: "
            "not comparable"
        )
        return v

    catch_only = rules_for(current.tier) is PICK_RULES
    for name, better in rules_for(current.tier):
        now, was = current.totals[name], baseline.totals[name]
        if now == was:
            continue
        worse = now < was if better == "higher" else now > was
        line = f"{name}: {was} -> {now}"
        if worse:
            v.passed = False
            v.failures.append(line)
        else:
            v.improved.append(line)

    was_rows = {r.id: r for r in baseline.rows}
    for row in current.rows:
        old = was_rows.get(row.id)
        if old is None:
            v.missing.append(row.id)
            continue
        if catch_only:
            if old.pick_key != row.pick_key:
                v.changed.append(
                    f"{row.id}: caught {old.caught_ripe}->{row.caught_ripe}  "
                    f"pick damage {old.pick_damage}->{row.pick_damage}  "
                    f"false {old.false_picks}->{row.false_picks}  "
                    f"unreachable {old.unreachable}->{row.unreachable}"
                )
        elif old.key != row.key:
            v.changed.append(
                f"{row.id}: picked {old.picked_ripe}->{row.picked_ripe}  "
                f"damage {old.damage_events}->{row.damage_events}  "
                f"false {old.false_picks}->{row.false_picks}  "
                f"unreachable {old.unreachable}->{row.unreachable}  "
                f"spilled {old.spilled}->{row.spilled}  "
                f"bruised {old.bruised}->{row.bruised}"
            )
    return v


def check_sensor_tracks_camera(
    tier: str = "smoke", seed: int = 1, tolerance: float = 0.08, log=print
) -> Verdict:
    """The cheap sensor model has to keep standing in for the camera.

    It is fitted to one detector on one set of scenes. Change the detector, the
    lighting or the layout and it quietly stops being a stand-in for anything,
    and every fast run after that is measuring a fiction. Nothing else in the
    bench would notice, so the gate checks it.

    It compares the catch rate, not the success rate. The sensor model stands
    in for perception, and perception's part is over once the berry is in the
    tray. What happens on the way to the punnet depends on where the berry
    landed in the tray, which differs between any two runs that cut it at all
    differently. When packing was added, the two paths caught exactly the same
    ripe berries in both tiers, yet packed success drifted 0.107 apart over the
    six smoke scenarios — three spills — and failed this check for a reason
    that had nothing to do with the sensor model.
    """
    cam = run_suite(tier=tier, seed=seed, detector="colour", log=lambda *_: None)
    sensor = run_suite(tier=tier, seed=seed, detector=None, log=lambda *_: None)
    gap = abs(cam.totals["catch_rate"] - sensor.totals["catch_rate"])
    ok = gap <= tolerance
    log(
        f"catch rate: camera {cam.totals['catch_rate']:.3f} vs sensor model "
        f"{sensor.totals['catch_rate']:.3f}  gap {gap:.3f} (allowed {tolerance})"
    )
    return Verdict(
        passed=ok,
        failures=[] if ok else [f"sensor model drifted {gap:.3f} from the camera"],
    )
