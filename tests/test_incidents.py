"""Flags read from a field log, with no ground truth to lean on."""

from harvestbench.incidents import PickRecord, flag


def record(**kw) -> PickRecord:
    base = dict(pick_id="d00", est_ripeness=0.8, reached=True, reach_error_m=0.002,
                cut_fired=True, tray_registered=True, peak_force_n=0.0, duration_s=8.0)
    return PickRecord(**(base | kw))


def kinds(rec: PickRecord) -> set[str]:
    return {i.kind for i in flag(rec)}


def test_a_berry_the_punnet_never_saw_is_flagged_as_spilled():
    assert "spilled" in kinds(record(place_cell=2, landed_cell=None))


def test_the_wrong_cup_is_a_watch_not_an_alarm():
    flags = flag(record(place_cell=2, landed_cell=3))
    assert [(i.kind, i.severity) for i in flags] == [("misplaced", "watch")]


def test_a_clean_placement_raises_nothing():
    assert kinds(record(place_cell=2, landed_cell=2)) == set()


def test_a_spill_after_the_catch_is_not_reported_as_a_drop():
    """The tray registered the catch; losing it later is a different failure."""
    rec = record(tray_registered=True, place_cell=0, landed_cell=None)
    assert "dropped" not in kinds(rec)


def test_the_catch_is_read_from_the_log_not_from_the_outcome():
    events = [
        {"event": "run.started", "detail": "S0001", "t": 0.0},
        {"event": "pick.started", "detail": "d00", "est_ripeness": 0.8, "t": 0.1},
        {"event": "arm.at_cut_point", "reached": True, "error_m": 0.002, "t": 1.0},
        {"event": "cutter.cut", "detail": "b00", "t": 1.1},
        {"event": "place.started", "detail": "b00", "cell": 0, "t": 3.0},
        {"event": "place.failed", "detail": "missed", "cell": 0, "landed_cell": None, "t": 5.0},
        {"event": "pick.failed", "outcome": "spilled", "caught": True, "peak_force_n": 0.0,
         "duration_s": 6.0, "t": 6.0},
    ]
    (rec,) = PickRecord.from_events(events)
    assert rec.tray_registered
    assert rec.place_cell == 0 and rec.landed_cell is None
    assert kinds(rec) == {"spilled"}


def test_stopping_short_of_the_cut_point_is_flagged_as_blocked():
    flags = flag(record(reached=False, reach_error_m=0.079, cut_fired=False,
                        tray_registered=False))
    assert [(i.kind, i.severity) for i in flags] == [("blocked", "high")]
    assert "79 mm" in flags[0].why


def test_a_small_miss_is_not_blocked():
    rec = record(reached=False, reach_error_m=0.006, cut_fired=False, tray_registered=False)
    assert "blocked" not in kinds(rec)
