"""Finding bad picks in field logs, where there is no ground truth.

The bench knows a berry was unripe, or that a stem tore. A machine in a
polytunnel knows none of that. It has what its own sensors recorded: what
perception estimated, what the arm commanded, how hard the cutter pressed,
whether the tray registered fruit, and how long it all took.

So the flags below read only those. Nothing here may touch the simulator's
truth — that is reserved for `validate()`, which measures how good the flags
are by running them over scenarios where the answer is known. Calibrate in the
lab, run on the farm: that is the whole arrangement.

The signals, and why a real machine has them:

  cutter force    motor current on the cutter drive. In sim it is attributed to
                  a specific berry; a real machine sees total resistance, which
                  is a weaker signal and the main thing this would overstate.
  tray registered a load cell or a tray camera. Standard on harvesters.
  ripeness margin perception's own output against the pick threshold. Free.
  reach error     commanded pose against achieved pose. Free from the encoders.
  punnet          which cup a camera over the punnet sees the fruit in, if any.
                  Packing lines carry one to count and grade the punnets.

What none of these can see is a bruise. It shows hours later, in the pack
house, so the bench measures it (landing speed) but no flag claims to.
"""

from dataclasses import dataclass, field

from .metrics import BORDERLINE
from .scenario import OVERRIPE, RIPE_MIN

# A press this hard means the blades were on fruit, not on the stem.
BRUISE_N = 2.0
TEAR_N = 6.0
# Within this much of the threshold, perception was guessing.
RIPENESS_MARGIN = 0.12
# The cutter ending further than this from where it was sent means something
# stopped it. Encoders give the achieved pose for free, so a real machine has
# this; it is the field-side signature of a leaf in the way.
BLOCKED_M = 0.010


@dataclass(frozen=True)
class Incident:
    kind: str
    severity: str  # "high" or "watch"
    why: str


@dataclass
class PickRecord:
    """One attempt, as a field machine would have logged it."""

    pick_id: str
    est_ripeness: float
    reached: bool
    reach_error_m: float
    cut_fired: bool
    tray_registered: bool
    peak_force_n: float
    duration_s: float
    tray_ripeness: float | None = None
    scenario_id: str = ""
    # The place step: the cup aimed at, and the cup the punnet camera saw the
    # fruit in afterwards. place_cell is None when nothing was carried there.
    place_cell: int | None = None
    landed_cell: int | None = None

    @classmethod
    def from_events(cls, events: list[dict]) -> list["PickRecord"]:
        """Rebuild attempts from a telemetry stream."""
        out, open_pick = [], None
        scenario = ""
        for e in events:
            if e["event"] == "run.started":
                scenario = e.get("detail", "")
            elif e["event"] == "pick.started":
                open_pick = {"pick_id": e["detail"], "est_ripeness": e.get("est_ripeness", 0.0),
                             "cut_fired": False, "scenario_id": scenario}
            elif open_pick is None:
                continue
            elif e["event"] == "arm.at_cut_point":
                open_pick["reached"] = e.get("reached", False)
                open_pick["reach_error_m"] = e.get("error_m", 0.0)
            elif e["event"] == "cutter.cut":
                open_pick["cut_fired"] = True
            elif e["event"] == "place.started":
                open_pick["place_cell"] = e.get("cell")
            elif e["event"] in ("place.completed", "place.failed"):
                open_pick["landed_cell"] = e.get("landed_cell")
            elif e["event"] in ("pick.completed", "pick.failed"):
                out.append(cls(
                    pick_id=open_pick["pick_id"],
                    est_ripeness=open_pick["est_ripeness"],
                    reached=open_pick.get("reached", False),
                    reach_error_m=open_pick.get("reach_error_m", 0.0),
                    cut_fired=open_pick["cut_fired"],
                    # The tray either registered fruit or it did not. That is
                    # the catch, not the packing: a berry lost on the way to
                    # the punnet was still caught.
                    tray_registered=e.get("caught", e.get("outcome") == "picked"),
                    peak_force_n=e.get("peak_force_n", 0.0),
                    duration_s=e.get("duration_s", 0.0),
                    tray_ripeness=e.get("tray_ripeness"),
                    scenario_id=open_pick["scenario_id"],
                    place_cell=open_pick.get("place_cell"),
                    landed_cell=open_pick.get("landed_cell"),
                ))
                open_pick = None
        return out


def flag(rec: PickRecord) -> list[Incident]:
    """Everything suspicious about one attempt, from its own record."""
    out = []
    if rec.peak_force_n > TEAR_N:
        out.append(Incident(
            "stem_tear", "high",
            f"cutter drew {rec.peak_force_n:.1f} N before cutting: it was on fruit, "
            "not on the stem",
        ))
    elif rec.peak_force_n > BRUISE_N:
        out.append(Incident(
            "bruise_risk", "watch",
            f"cutter pressed {rec.peak_force_n:.1f} N on attached fruit",
        ))

    if rec.cut_fired and not rec.tray_registered:
        out.append(Incident(
            "dropped", "high", "the cut fired but the tray never registered fruit",
        ))

    if not rec.reached and rec.reach_error_m > BLOCKED_M and rec.peak_force_n <= TEAR_N:
        out.append(Incident(
            "blocked", "high",
            f"the cutter stopped {rec.reach_error_m * 1000:.0f} mm short of the cut point "
            "it was sent to: something was in the way",
        ))

    if rec.place_cell is not None:
        if rec.landed_cell is None:
            out.append(Incident(
                "spilled", "high",
                "the berry was carried to the punnet but the punnet camera never saw it",
            ))
        elif rec.landed_cell != rec.place_cell:
            out.append(Incident(
                "misplaced", "watch",
                f"aimed at cup {rec.place_cell}, the punnet camera saw it in cup "
                f"{rec.landed_cell}",
            ))

    if rec.reached and not rec.cut_fired and rec.peak_force_n <= TEAR_N:
        out.append(Incident(
            "closed_on_nothing", "watch",
            "the arm reached the commanded pose but no stem was in the blades",
        ))

    if rec.tray_registered:
        # Both bounds. Looking only at the lower one missed four of the seven
        # bad picks in the first pass over the logs: they were not unripe, they
        # were past it, and nothing was watching that end.
        tray = rec.tray_ripeness
        if tray is not None and not (RIPE_MIN <= tray < OVERRIPE):
            early = tray < RIPE_MIN
            out.append(Incident(
                "unripe_picked" if early else "overripe_picked", "high",
                f"the tray camera read {tray:.2f}, "
                f"{'short of' if early else 'past'} the "
                f"{RIPE_MIN if early else OVERRIPE} mark; the survey camera had "
                f"said {rec.est_ripeness:.2f}",
            ))
        elif tray is None and abs(rec.est_ripeness - RIPE_MIN) < RIPENESS_MARGIN:
            # Only when nothing looked again. A tray reading inside the window
            # has already answered the question, and flagging it anyway was
            # most of the noise in the first version of this.
            out.append(Incident(
                "unripe_risk", "watch",
                f"picked on an estimate of {rec.est_ripeness:.2f}, within "
                f"{RIPENESS_MARGIN} of the {RIPE_MIN} threshold, and the tray "
                "camera saw nothing to confirm it",
            ))
    return out


@dataclass
class Validation:
    """How well a flag predicts the failure it is standing in for."""

    kind: str
    flagged: int = 0
    real: int = 0
    hits: int = 0
    examples: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.hits / self.flagged if self.flagged else 0.0

    @property
    def recall(self) -> float:
        return self.hits / self.real if self.real else 0.0

    def line(self) -> str:
        if not self.real:
            return (
                f"{self.kind:<18} flagged {self.flagged:<4} actually bad 0    "
                "— nothing of this kind happened; every flag is a false alarm"
            )
        return (
            f"{self.kind:<18} flagged {self.flagged:<4} actually bad {self.real:<4} "
            f"caught {self.hits:<4} precision {self.precision:5.0%} recall {self.recall:5.0%}"
        )


def validate(results: list) -> dict[str, Validation]:
    """Score the flags against what the simulator knows.

    This is the step the farm cannot do, and the reason the lab exists: here the
    answer is known, so a flag can be shown to catch what it claims to catch
    before anyone trusts it on a log from a real machine.
    """
    kinds = ("stem_tear", "unripe_risk", "unripe_picked", "overripe_picked", "dropped",
             "spilled", "misplaced", "blocked")
    out = {k: Validation(kind=k) for k in kinds}

    for r in results:
        truth = {b.berry_id: b for b in r.scenario.berries}
        by_label = {p.berry_id: p for p in r.picks}
        for rec in PickRecord.from_events(r.telemetry.records):
            p = by_label.get(rec.pick_id)
            if p is None:
                continue
            flags = {i.kind for i in flag(rec)}
            cut = truth.get(p.cut_berry_id) if p.cut_berry_id else None
            actual = {
                "stem_tear": p.stem_torn,
                "dropped": p.dropped,
                "spilled": p.spilled,
                "misplaced": p.packed and not p.placed,
                "blocked": p.outcome == "unreachable",
                # The one a machine genuinely cannot see: ripe fruit is what the
                # pack house would reject it for.
                "unripe_risk": bool(
                    p.caught and cut and cut.ripeness < RIPE_MIN - BORDERLINE
                ),
                # Borderline fruit is excluded. A berry 0.01 under the line is
                # the same berry as one 0.01 over it, and scoring a flag on
                # those measures the threshold rather than the detector.
                "unripe_picked": bool(
                    p.caught and cut and cut.ripeness < RIPE_MIN - BORDERLINE
                ),
                "overripe_picked": bool(
                    p.caught and cut and cut.ripeness >= OVERRIPE + BORDERLINE
                ),
            }
            for kind, v in out.items():
                v.flagged += kind in flags
                v.real += actual[kind]
                if kind in flags and actual[kind]:
                    v.hits += 1
                    if len(v.examples) < 3:
                        v.examples.append(f"{rec.scenario_id}/{rec.pick_id}")
    return out
