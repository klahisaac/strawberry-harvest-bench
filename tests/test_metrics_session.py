"""Scoring arithmetic, and a session that runs end to end."""

import json

from harvestbench import metrics, scenario
from harvestbench.cell import PickResult
from harvestbench.session import RunConfig, run_scenario, run_session


class FakeResult:
    """A ScenarioResult stand-in, so the scoring can be checked by hand."""

    def __init__(self, sc, picks, skipped=(), missed=()):
        self.scenario = sc
        self.picks = picks
        self.targeted = [p.cut_berry_id for p in picks if p.cut_berry_id]
        self.skipped = list(skipped)
        self.missed_undetected = list(missed)
        self.duration_s = 1.0


def test_bucket_boundaries():
    assert metrics.bucket_of(0.0) == "clear"
    assert metrics.bucket_of(0.19) == "clear"
    assert metrics.bucket_of(0.20) == "partial"
    assert metrics.bucket_of(0.49) == "partial"
    assert metrics.bucket_of(0.50) == "heavy"
    assert metrics.bucket_of(1.0) == "heavy"


def test_success_rate_counts_only_ripe_berries():
    sc = scenario.generate(seed=21, n_berries=6)
    ripe = [b for b in sc.berries if b.should_pick]
    unripe = [b for b in sc.berries if not b.should_pick]
    picks = [PickResult(berry_id="d00", cut_berry_id=ripe[0].berry_id, reached=True,
                        cut=True, caught=True, place_cell=0, landed_cell=0,
                        duration_s=1.5)]
    m = metrics.score([FakeResult(sc, picks)])
    assert m.ripe_total == len(ripe)
    assert m.picked_ripe == 1
    assert m.success_rate == 1 / len(ripe)
    assert m.false_picks == 0
    if unripe:
        picks.append(PickResult(berry_id="d01", cut_berry_id=unripe[0].berry_id,
                                reached=True, cut=True, caught=True, place_cell=1,
                                landed_cell=1, duration_s=1.0))
        assert metrics.score([FakeResult(sc, picks)]).false_picks == 1


def test_damage_adds_torn_stems_and_knocks():
    sc = scenario.generate(seed=22, n_berries=6)
    ids = [b.berry_id for b in sc.berries]
    picks = [
        PickResult(berry_id="d00", cut_berry_id=ids[0], reached=True, stem_torn=True,
                   duration_s=1.0),
        PickResult(berry_id="d01", cut_berry_id=ids[1], reached=True, cut=True,
                   caught=True, place_cell=0, landed_cell=0, knocked=(ids[2], ids[3]),
                   duration_s=1.0),
    ]
    m = metrics.score([FakeResult(sc, picks)])
    assert m.stem_torn == 1
    assert m.knock_events == 2
    assert m.damage_events == 3


def _caught(sc, **place):
    """A ripe berry cut and caught, with the place step's result filled in."""
    ripe = next(b for b in sc.berries if b.should_pick)
    return PickResult(berry_id="d00", cut_berry_id=ripe.berry_id, reached=True,
                      cut=True, caught=True, place_cell=0, duration_s=1.0, **place)


def test_a_berry_lost_before_the_punnet_is_not_a_success():
    """Caught is not harvested. Fruit on the floor is not in the success rate."""
    sc = scenario.generate(seed=21, n_berries=6)
    p = _caught(sc, landed_cell=None, spilled=True)
    m = metrics.score([FakeResult(sc, [p])])
    assert p.outcome == "spilled"
    assert m.picked_ripe == 0 and m.spilled == 1 and m.packed == 0
    # It was still caught: the catch rate is perception's half of the job.
    assert m.caught_ripe == 1 and m.catch_rate > m.success_rate == 0.0


def test_the_wrong_cup_is_packed_but_not_placed():
    sc = scenario.generate(seed=21, n_berries=6)
    m = metrics.score([FakeResult(sc, [_caught(sc, landed_cell=3)])])
    assert m.picked_ripe == 1
    assert m.packed == 1 and m.placed == 0 and m.misplaced == 1


def test_a_hard_landing_is_a_bruise_and_counts_as_damage():
    sc = scenario.generate(seed=21, n_berries=6)
    soft = metrics.score([FakeResult(sc, [_caught(sc, landed_cell=0, impact_speed_m_s=0.5)])])
    hard = metrics.score([FakeResult(sc, [_caught(sc, landed_cell=0, impact_speed_m_s=1.0)])])
    assert soft.bruised == 0 and soft.damage_events == 0
    assert hard.bruised == 1 and hard.damage_events == 1
    # Bruised fruit is still in the punnet, so it still counts as picked.
    assert hard.picked_ripe == 1


def test_missed_ripe_is_split_by_cause():
    sc = scenario.generate(seed=23, n_berries=6)
    ripe = [b.berry_id for b in sc.berries if b.should_pick]
    assert len(ripe) >= 2
    m = metrics.score([FakeResult(sc, [], skipped=[ripe[0]], missed=[ripe[1]])])
    assert m.missed_skipped == 1
    assert m.missed_undetected == 1


def test_unreachable_outcome_is_counted():
    sc = scenario.generate(seed=24, n_berries=4)
    picks = [PickResult(berry_id="d00", reached=False, duration_s=3.0)]
    m = metrics.score([FakeResult(sc, picks)])
    assert m.unreachable == 1
    assert m.attempts == 1


def test_empty_score_does_not_divide_by_zero():
    m = metrics.score([])
    assert m.success_rate == 0.0
    assert m.as_dict()["success_rate"] == 0.0


def test_pick_result_outcome_precedence():
    assert PickResult("d0", cut_berry_id="b", reached=True, cut=True,
                      caught=True).outcome == "picked"
    assert PickResult("d0", cut_berry_id="b", reached=True, cut=True,
                      caught=True, spilled=True).outcome == "spilled"
    assert PickResult("d0", cut_berry_id="b", reached=True,
                      stem_torn=True).outcome == "stem_torn"
    assert PickResult("d0", cut_berry_id="b", reached=True, cut=True,
                      dropped=True).outcome == "dropped"
    assert PickResult("d0", reached=False).outcome == "unreachable"
    assert PickResult("d0", reached=True).outcome == "missed"


def test_one_scenario_session_runs_and_scores():
    sc = scenario.generate(seed=25, n_berries=4)
    r = run_scenario(sc, RunConfig(seed=25, n_berries=4))
    assert len(r.picks) == len(r.targeted)
    assert r.duration_s > 0
    assert "<mujoco" in r.mjcf
    # Every berry is accounted for exactly once.
    seen = set(r.targeted) | set(r.skipped) | set(r.missed_undetected)
    assert seen == {b.berry_id for b in sc.berries}


def test_session_writes_artifacts(tmp_path):
    cfg = RunConfig(seed=26, scenarios=1, n_berries=4, out_dir=tmp_path)
    m, results = run_session(cfg, log=lambda *_: None)
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "config.json").exists()
    written = json.loads((tmp_path / "metrics.json").read_text())
    assert written["success_rate"] == round(m.success_rate, 4)
    run_dir = tmp_path / results[0].scenario.scenario_id
    assert (run_dir / "telemetry.jsonl").exists()
    assert (run_dir / "scene.xml").exists()


def test_in_memory_session_writes_nothing(tmp_path):
    run_session(RunConfig(seed=27, scenarios=1, n_berries=3), log=lambda *_: None)
    assert not list(tmp_path.iterdir())


def test_session_is_reproducible():
    cfg = RunConfig(seed=28, scenarios=2, n_berries=4)
    a, _ = run_session(cfg, log=lambda *_: None)
    b, _ = run_session(cfg, log=lambda *_: None)
    assert a.as_dict() == b.as_dict()


def test_observer_hooks_fire():
    calls = {"observe": 0, "pick": 0}

    class Spy:
        def on_observe(self, **kw):
            calls["observe"] += 1

        def on_pick(self, **kw):
            calls["pick"] += 1

    sc = scenario.generate(seed=29, n_berries=5)
    r = run_scenario(sc, RunConfig(seed=29, n_berries=5), observer=Spy())
    assert calls["observe"] == 1
    assert calls["pick"] == len(r.picks)
