"""The scenario suite, the diff, and what the gate blocks on."""

import json

import pytest

from harvestbench.suite import (
    PICK_RULES,
    PINNED,
    RULES,
    TIERS,
    rules_for,
    ScenarioRow,
    SuiteResult,
    _aggregate,
    compare,
    run_suite,
)


def row(id_, picked=3, ripe=5, damage=0, false=0, unreachable=1, attempts=4, **extra):
    return ScenarioRow(
        id=id_, ripe_total=ripe, picked_ripe=picked, damage_events=damage,
        false_picks=false, unreachable=unreachable, attempts=attempts, **extra,
    )


def result(rows, detector="colour", policy="baseline", tier="smoke"):
    return SuiteResult(
        tier=tier, detector=detector, policy=policy, rows=rows, totals=_aggregate(rows)
    )


def test_aggregate_sums_and_divides():
    t = _aggregate([row("A", picked=2, ripe=4), row("B", picked=3, ripe=6, damage=2)])
    assert t["ripe_total"] == 10
    assert t["picked_ripe"] == 5
    assert t["success_rate"] == 0.5
    assert t["damage_events"] == 2


def test_aggregate_of_nothing_does_not_divide_by_zero():
    assert _aggregate([])["success_rate"] == 0.0


def test_an_identical_run_passes():
    a = result([row("A"), row("B")])
    assert compare(a, result([row("A"), row("B")])).passed


def test_a_drop_in_success_fails():
    v = compare(result([row("A", picked=1)]), result([row("A", picked=4)]))
    assert not v.passed
    assert any("success_rate" in f for f in v.failures)


def test_more_damage_fails_even_when_success_rises():
    """The interesting case: better on average, one new damaged berry."""
    v = compare(
        result([row("A", picked=4, damage=1), row("B", picked=4)]),
        result([row("A", picked=3, damage=0), row("B", picked=4)]),
    )
    assert not v.passed
    assert any("damage_events" in f for f in v.failures)
    assert any("success_rate" in i for i in v.improved)


def test_improvements_are_reported_but_do_not_fail():
    v = compare(result([row("A", picked=5)]), result([row("A", picked=3)]))
    assert v.passed
    assert v.improved


def test_the_scenario_that_moved_is_named():
    v = compare(
        result([row("A", picked=3), row("B", picked=1, damage=2)]),
        result([row("A", picked=3), row("B", picked=3, damage=0)]),
    )
    assert len(v.changed) == 1
    assert v.changed[0].startswith("B:")
    assert "3->1" in v.changed[0]


def test_a_new_scenario_is_flagged_not_silently_accepted():
    v = compare(result([row("A"), row("C")]), result([row("A"), row("B")]))
    assert v.missing == ["C"]


def test_runs_against_a_different_setup_are_refused():
    v = compare(result([row("A")], detector="colour"), result([row("A")], detector=None))
    assert not v.passed
    assert "not comparable" in v.failures[0]


def test_rules_cover_the_headline_numbers():
    names = {n for n, _ in RULES}
    assert {"success_rate", "damage_events", "false_picks"} <= names


def test_round_trips_through_json(tmp_path):
    a = result([row("A", picked=2), row("B", damage=3)])
    path = a.save(tmp_path / "b.json")
    back = SuiteResult.from_dict(json.loads(path.read_text()))
    assert back.totals == a.totals
    assert [r.id for r in back.rows] == ["A", "B"]
    assert compare(a, back).passed


def test_report_names_the_verdict():
    v = compare(result([row("A", picked=0)]), result([row("A", picked=4)]))
    assert v.report().startswith("FAIL")
    assert "success_rate" in v.report()


@pytest.mark.parametrize("tier", sorted(TIERS))
def test_tiers_are_ordered(tier):
    assert TIERS["smoke"] < TIERS["full"]
    assert TIERS[tier] > 0


def test_the_suite_runs_and_is_reproducible():
    """Pinned seeds and a fixed timestep: the diff is exact, not statistical."""
    a = run_suite(tier="smoke", seed=1, workers=2, log=lambda *_: None)
    b = run_suite(tier="smoke", seed=1, workers=2, log=lambda *_: None)
    assert a.totals == b.totals
    assert [r.key for r in a.rows] == [r.key for r in b.rows]
    assert len(a.rows) == TIERS["smoke"]
    assert compare(a, b).passed


def test_a_different_seed_gives_different_scenarios():
    a = run_suite(tier="smoke", seed=1, workers=2, log=lambda *_: None)
    b = run_suite(tier="smoke", seed=100, workers=2, log=lambda *_: None)
    assert [r.id for r in a.rows] != [r.id for r in b.rows]


# ---- the demo tier: picking only ------------------------------------------


def test_the_demo_tier_judges_picking_not_packing():
    assert rules_for("demo") is PICK_RULES
    assert rules_for("smoke") is RULES
    names = {n for n, _ in PICK_RULES}
    assert {"catch_rate", "pick_damage", "false_picks"} <= names
    assert not names & {"success_rate", "damage_events", "spilled", "bruised"}


def test_a_spill_or_a_bruise_does_not_fail_the_demo_tier():
    was = result([row("A", caught_ripe=5, picked=5, damage=0)], tier="demo")
    now = result([row("A", caught_ripe=5, picked=4, damage=2, spilled=1, bruised=2)],
                 tier="demo")
    v = compare(now, was)
    assert v.passed and not v.changed


def test_a_lost_catch_fails_the_demo_tier_and_names_the_scenario():
    was = result([row("A", caught_ripe=5)], tier="demo")
    now = result([row("A", caught_ripe=4)], tier="demo")
    v = compare(now, was)
    assert not v.passed
    assert any("catch_rate" in f for f in v.failures)
    assert any(c.startswith("A:") for c in v.changed)


def test_a_torn_stem_fails_the_demo_tier():
    was = result([row("A", caught_ripe=5, pick_damage=0)], tier="demo")
    now = result([row("A", caught_ripe=5, pick_damage=1, damage=1)], tier="demo")
    assert not compare(now, was).passed


def test_different_tiers_are_not_compared():
    assert not compare(result([row("A")], tier="demo"), result([row("A")])).passed


def test_the_demo_tier_runs_its_pinned_scenarios():
    res = run_suite(tier="demo", seed=1, workers=2, log=lambda *_: None)
    assert [r.id for r in res.rows] == [f"S{s:04d}" for s in PINNED["demo"]]
    # Chosen because every ripe berry is caught with nothing torn or knocked.
    assert res.totals["catch_rate"] == 1.0
    assert res.totals["pick_damage"] == 0
