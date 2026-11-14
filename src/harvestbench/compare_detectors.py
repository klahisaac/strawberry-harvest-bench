"""The two detectors on the same scenes, scored against ground truth.

    uv run --group ml python -m harvestbench.compare_detectors --tier full

Perception only: no arm moves. Each detector reads the same survey frame of
every scenario in the tier, its detections are matched to the real berries,
and the errors are bucketed by how hidden each berry measured — which is where
the two are expected to differ.

The cut-point error is the one that reaches the arm. It is the distance from
where a detection would send the cutter to where the berry's stem really is.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing

import numpy as np

from .metrics import BUCKETS, bucket_of
from .suite import PINNED, TIERS


def _one(seed: int) -> list[dict]:
    from .cell import MuJoCoCell
    from .scenario import generate
    from .session import DETECTORS, match_detections

    sc = generate(seed=seed, n_berries=6, scenario_id=f"S{seed:04d}")
    rows = []
    for name, make in DETECTORS.items():
        cell = MuJoCoCell(sc, seed=1, detector=make())
        occlusion = cell.occlusion
        detections = cell.observe()
        matched = match_detections(sc, detections)
        by_berry = {m: d for d in detections if (m := matched.get(d.berry_id))}
        for b in sc.berries:
            d = by_berry.get(b.berry_id)
            rows.append({
                "detector": name, "bucket": bucket_of(occlusion.get(b.berry_id, 1.0)),
                "detected": d is not None,
                "pos_mm": None if d is None else float(np.linalg.norm(np.subtract(d.pos, b.pos))) * 1000,
                "cut_mm": None if d is None else float(np.linalg.norm(d.cut_point - np.array(b.cut_point))) * 1000,
                "ripeness": None if d is None else abs(d.ripeness - b.ripeness),
                # The decision that follows from the estimate: pick or leave.
                "decision_ok": None if d is None else (d.ripeness >= 0.6) == (b.ripeness >= 0.6),
            })
        rows.append({"detector": name, "bucket": "_extra",
                     "extra": sum(1 for d in detections if not matched.get(d.berry_id))})
    return rows


def compare(tier: str = "full", seed: int = 1, workers: int = 12) -> dict:
    seeds = PINNED.get(tier) or [seed + i for i in range(TIERS[tier])]
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(min(workers, len(seeds)), mp_context=ctx) as pool:
        rows = [r for rs in pool.map(_one, seeds) for r in rs]
    out = {}
    for name in sorted({r["detector"] for r in rows}):
        mine = [r for r in rows if r["detector"] == name]
        table = {}
        for bucket in [b for b, _, _ in BUCKETS] + ["all"]:
            sel = [r for r in mine if r["bucket"] != "_extra"
                   and (bucket == "all" or r["bucket"] == bucket)]
            hit = [r for r in sel if r["detected"]]
            mean = lambda k: round(float(np.mean([r[k] for r in hit])), 3) if hit else None  # noqa: E731
            table[bucket] = {
                "berries": len(sel), "detected": len(hit),
                "pos_mm": mean("pos_mm"), "cut_mm": mean("cut_mm"),
                "ripeness_mae": mean("ripeness"),
                "wrong_decisions": sum(1 for r in hit if not r["decision_ok"]),
            }
        table["false_detections"] = sum(r.get("extra", 0) for r in mine)
        out[name] = table
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m harvestbench.compare_detectors")
    p.add_argument("--tier", choices=sorted(TIERS), default="full")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    result = compare(args.tier)
    if args.json:
        print(json.dumps(result, indent=1))
        return
    print(f"{'detector':9} {'occlusion':9} {'found':>9} {'position':>9} {'cut point':>10} "
          f"{'ripeness':>9} {'wrong pick/leave':>17}")
    for name, table in result.items():
        for bucket in [b for b, _, _ in BUCKETS] + ["all"]:
            t = table[bucket]
            if not t["berries"]:
                continue
            print(f"{name:9} {bucket:9} {t['detected']:>4}/{t['berries']:<4} "
                  f"{t['pos_mm']:>7.1f}mm {t['cut_mm']:>8.1f}mm {t['ripeness_mae']:>9.3f} "
                  f"{t['wrong_decisions']:>17}")
        print(f"{name:9} false detections: {table['false_detections']}")


if __name__ == "__main__":
    main()
