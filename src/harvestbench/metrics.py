"""Scoring a run against the scenario's ground truth.

Harvesting has no single number to minimize. Success rate, damage, missed ripe
fruit and cycle time trade against each other, and a change that improves one
while quietly worsening another is exactly what the regression gate has to
catch. So the result is a vector, and every field here is something an
operations team would actually ask about.
"""

from dataclasses import dataclass, field

import numpy as np

# Occlusion buckets, so "it got worse" can be localized.
BUCKETS = (("clear", 0.0, 0.20), ("partial", 0.20, 0.50), ("heavy", 0.50, 1.01))

# Fruit this close to a ripeness bound is the same fruit either side of it.
# Counting those as errors measures the threshold, not the robot.
BORDERLINE = 0.03


def bucket_of(occlusion: float) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= occlusion < hi:
            return name
    return "heavy"


@dataclass
class Metrics:
    scenarios: int = 0
    ripe_total: int = 0
    picked_ripe: int = 0
    false_picks: int = 0
    borderline_picks: int = 0
    missed_undetected: int = 0
    missed_skipped: int = 0
    stem_torn: int = 0
    knock_events: int = 0
    # The place step. Packed is in the punnet at all; placed is in the cup it
    # was aimed at. Misplaced fruit is sellable after a packer moves it;
    # spilled fruit is not, and neither is a bruised berry.
    caught_ripe: int = 0  # ripe berries cut and caught, packed or not
    packed: int = 0
    placed: int = 0
    misplaced: int = 0
    spilled: int = 0
    bruised: int = 0
    unreachable: int = 0
    attempts: int = 0
    cycle_p50_s: float = 0.0
    cycle_p95_s: float = 0.0
    by_bucket: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Ripe berries packed, over ripe berries present.

        Packed, not caught. A berry cut and caught and then lost on the way to
        the punnet is fruit on the floor, and counting the catch as the
        success is how 113 of 117 such berries went unnoticed.
        """
        return self.picked_ripe / self.ripe_total if self.ripe_total else 0.0

    @property
    def catch_rate(self) -> float:
        """Ripe berries caught, over ripe berries present.

        Everything up to the catch is decided by perception and the approach;
        everything after it is the carry and the drop. This is the first half
        on its own, which is what the sensor model is a stand-in for.
        """
        return self.caught_ripe / self.ripe_total if self.ripe_total else 0.0

    @property
    def pick_damage(self) -> int:
        """Damage done getting the berry off the plant: torn stems and knocks."""
        return self.stem_torn + self.knock_events

    @property
    def damage_events(self) -> int:
        return self.pick_damage + self.bruised

    def as_dict(self) -> dict:
        d = {
            "scenarios": self.scenarios,
            "ripe_total": self.ripe_total,
            "picked_ripe": self.picked_ripe,
            "success_rate": round(self.success_rate, 4),
            "catch_rate": round(self.catch_rate, 4),
            "false_picks": self.false_picks,
            "borderline_picks": self.borderline_picks,
            "missed_undetected": self.missed_undetected,
            "missed_skipped": self.missed_skipped,
            "stem_torn": self.stem_torn,
            "knock_events": self.knock_events,
            "packed": self.packed,
            "placed": self.placed,
            "misplaced": self.misplaced,
            "spilled": self.spilled,
            "bruised": self.bruised,
            "pick_damage": self.pick_damage,
            "damage_events": self.damage_events,
            "unreachable": self.unreachable,
            "attempts": self.attempts,
            "cycle_p50_s": round(self.cycle_p50_s, 3),
            "cycle_p95_s": round(self.cycle_p95_s, 3),
        }
        for name, _, _ in BUCKETS:
            b = self.by_bucket.get(name, {})
            d[f"success_{name}"] = (
                round(b.get("picked", 0) / b["ripe"], 4) if b.get("ripe") else None
            )
        return d

    def summary(self) -> str:
        parts = [
            f"success {self.success_rate:.1%} ({self.picked_ripe}/{self.ripe_total} ripe)",
            f"damage {self.damage_events} (bruised {self.bruised})",
            f"placed {self.placed}/{self.packed + self.spilled}"
            + (f" (+{self.misplaced} misplaced)" if self.misplaced else ""),
            f"false picks {self.false_picks}",
            f"unreachable {self.unreachable}",
            f"cycle p50 {self.cycle_p50_s:.2f}s p95 {self.cycle_p95_s:.2f}s",
        ]
        by = " ".join(
            f"{name}={self.by_bucket[name]['picked']}/{self.by_bucket[name]['ripe']}"
            for name, _, _ in BUCKETS
            if self.by_bucket.get(name, {}).get("ripe")
        )
        return "  ".join(parts) + (f"\n  by occlusion: {by}" if by else "")


def score(results: list) -> Metrics:
    """Aggregate ScenarioResults into one metrics vector."""
    m = Metrics(scenarios=len(results))
    cycles: list[float] = []
    buckets: dict[str, dict[str, int]] = {n: {"ripe": 0, "picked": 0} for n, _, _ in BUCKETS}

    for r in results:
        truth = {b.berry_id: b for b in r.scenario.berries}
        occ = getattr(r, "occlusion", None) or {}
        # Scored on the berry actually cut, not the one aimed at. With a camera
        # in the loop those differ, and crediting the aim would hide it. And on
        # the berry packed, not caught: what reaches the punnet is the harvest.
        picked_ok = {p.cut_berry_id for p in r.picks if p.packed}
        caught = {p.cut_berry_id for p in r.picks if p.caught}

        for b in r.scenario.berries:
            if not b.should_pick:
                continue
            m.ripe_total += 1
            bkt = buckets[bucket_of(occ.get(b.berry_id, b.occlusion))]
            bkt["ripe"] += 1
            m.caught_ripe += b.berry_id in caught
            if b.berry_id in picked_ok:
                m.picked_ripe += 1
                bkt["picked"] += 1

        for bid in r.missed_undetected:
            if truth[bid].should_pick:
                m.missed_undetected += 1
        for bid in r.skipped:
            if truth[bid].should_pick:
                m.missed_skipped += 1

        for p in r.picks:
            m.attempts += 1
            cycles.append(p.duration_s)
            if p.caught and p.cut_berry_id and not truth[p.cut_berry_id].should_pick:
                from .scenario import OVERRIPE, RIPE_MIN

                ripeness = truth[p.cut_berry_id].ripeness
                near = min(abs(ripeness - RIPE_MIN), abs(ripeness - OVERRIPE))
                if near <= BORDERLINE:
                    m.borderline_picks += 1
                else:
                    m.false_picks += 1
            if p.stem_torn:
                m.stem_torn += 1
            if p.caught:
                m.packed += p.packed
                m.placed += p.placed
                m.misplaced += p.packed and not p.placed
                m.spilled += not p.packed
                m.bruised += p.bruised
            m.knock_events += len(p.knocked)
            if p.outcome == "unreachable":
                m.unreachable += 1

    if cycles:
        m.cycle_p50_s = float(np.percentile(cycles, 50))
        m.cycle_p95_s = float(np.percentile(cycles, 95))
    m.by_bucket = buckets
    return m
