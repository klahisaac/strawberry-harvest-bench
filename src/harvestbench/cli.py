"""Command line: `harvest run` for one session, `harvest scene` to dump MJCF."""

import argparse
import json
from pathlib import Path

from .scenario import generate
from .scene import build
from .session import DETECTORS, POLICIES, RunConfig, run_session
from .suite import TIERS, SuiteResult, check_sensor_tracks_camera, compare, run_suite


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="harvest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run scenarios and score them")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--scenarios", type=int, default=1)
    run.add_argument("--berries", type=int, default=6)
    run.add_argument("--policy", choices=sorted(POLICIES), default="baseline")
    run.add_argument("--detector", choices=sorted(DETECTORS), default=None,
                     help="read the camera instead of the simulator's ground truth")
    run.add_argument("--out", type=Path, default=None, help="write artifacts here")

    scene = sub.add_parser("scene", help="print the MJCF for one scenario")
    scene.add_argument("--seed", type=int, default=0)
    scene.add_argument("--berries", type=int, default=6)

    suite = sub.add_parser("suite", help="run a tier of scenarios in parallel")
    suite.add_argument("--tier", choices=sorted(TIERS), default="full")
    suite.add_argument("--seed", type=int, default=1)
    suite.add_argument("--berries", type=int, default=6)
    suite.add_argument("--detector", choices=sorted(DETECTORS), default="colour")
    suite.add_argument("--no-detector", dest="detector", action="store_const", const=None,
                       help="use the fitted sensor model instead of the camera")
    suite.add_argument("--workers", type=int, default=None)
    suite.add_argument("--out", type=Path, default=None)

    gate = sub.add_parser("gate", help="run a tier and diff it against the baseline")
    gate.add_argument("--tier", choices=sorted(TIERS), default="smoke")
    gate.add_argument("--seed", type=int, default=1)
    gate.add_argument("--detector", choices=sorted(DETECTORS), default="colour")
    gate.add_argument("--no-detector", dest="detector", action="store_const", const=None)
    gate.add_argument("--workers", type=int, default=None)
    gate.add_argument("--baseline", type=Path, default=None,
                      help="defaults to baselines/<tier>-<detector>.json")
    gate.add_argument("--update", action="store_true",
                      help="record this run as the new baseline instead of judging it")
    gate.add_argument("--skip-tracking", action="store_true",
                      help="skip the check that the sensor model still matches the camera")

    inc = sub.add_parser("incidents", help="flag bad picks in a run's telemetry")
    inc.add_argument("run_dir", type=Path, help="a directory written by `harvest run --out`")

    bake = sub.add_parser("demo-bake", help="build the static demo page's data and videos")
    bake.add_argument("--agent", action="store_true",
                      help="run the AI agent on a fresh copy of the code first")

    args = parser.parse_args(argv)

    if args.cmd == "scene":
        print(build(generate(seed=args.seed, n_berries=args.berries)))
        return

    if args.cmd == "demo-bake":
        from .demobake import bake as run_bake

        run_bake(agent=args.agent)
        return

    if args.cmd == "incidents":
        from .incidents import PickRecord, flag

        logs = sorted(args.run_dir.glob("*/telemetry.jsonl"))
        if not logs:
            raise SystemExit(f"no telemetry under {args.run_dir}")
        total = flagged = 0
        for log in logs:
            events = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
            for rec in PickRecord.from_events(events):
                total += 1
                issues = flag(rec)
                if not issues:
                    continue
                flagged += 1
                print(f"\n{rec.scenario_id}/{rec.pick_id}")
                for i in issues:
                    print(f"  [{i.severity}] {i.kind}: {i.why}")
        print(f"\n{flagged} of {total} attempts flagged")
        return

    if args.cmd == "suite":
        res = run_suite(tier=args.tier, seed=args.seed, n_berries=args.berries,
                        detector=args.detector, workers=args.workers)
        print("\n" + json.dumps(res.totals, indent=2))
        if args.out:
            print("wrote", res.save(args.out))
        return

    if args.cmd == "gate":
        label = args.detector or "sensor"
        path = args.baseline or Path("baselines") / f"{args.tier}-{label}.json"
        res = run_suite(tier=args.tier, seed=args.seed, detector=args.detector,
                        workers=args.workers)
        if args.update:
            print("\nrecorded baseline:", res.save(path))
            return
        if not path.exists():
            raise SystemExit(f"no baseline at {path}; record one with --update")
        verdict = compare(res, SuiteResult.from_dict(json.loads(path.read_text())))
        print("\n" + verdict.report())
        ok = verdict.passed
        if not args.skip_tracking:
            print()
            tracking = check_sensor_tracks_camera(tier=args.tier, seed=args.seed)
            print(tracking.report())
            ok = ok and tracking.passed
        raise SystemExit(0 if ok else 1)

    cfg = RunConfig(
        seed=args.seed,
        scenarios=args.scenarios,
        n_berries=args.berries,
        policy=args.policy,
        detector=args.detector,
        out_dir=args.out,
    )
    m, _ = run_session(cfg)
    print("\n" + m.summary())
    if args.out:
        print(f"\nartifacts in {args.out}")


if __name__ == "__main__":
    main()
