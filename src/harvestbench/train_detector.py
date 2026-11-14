"""Train the learned berry detector on scenes the simulator renders and labels.

    uv run --group ml python -m harvestbench.train_detector

Nothing is annotated by hand. Each training scene is built, rendered through
the survey camera, and labelled from what the simulator knows: every berry's
centre, full size, ripeness and distance, whatever hangs in front of it. Half
the scenes are ordinary gutters; half are clusters, with fruit touching and
overlapping, because that is where a detector that only measures what it can
see goes wrong.

Training seeds start at 100000. The tier scenarios (seeds 1-40) and the demo's
photographed cluster are held out entirely, so what the gate measures is
performance on scenes the network has never been shown.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import time

import numpy as np

from .learned import (
    CHANNELS, DEPTH_REF_M, DEPTH_SPAN_M, SIZE_SCALE_PX, STRIDE, WEIGHTS, decode,
    encode_input, make_net,
)
from .scenario import BERRY_RADIUS, BERRY_Y, BERRY_Z, Berry, Scenario, generate

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "runs" / "detector-data"
SIZE = (640, 480)  # the survey frame the bench uses
SEED0 = 100_000
MIN_VISIBLE_PX = 20  # below this there is nothing of the berry to learn from


# ---- scenes ------------------------------------------------------------------


def cluster_scenario(seed: int) -> Scenario:
    """A gutter of small clusters: fruit beside, above and in front of fruit.

    Berries may overlap in the picture but never in space, so the physics has
    nothing to push apart: each new berry sits either a berry's depth in front
    of its neighbours or clear of them sideways.
    """
    rng = np.random.default_rng(seed)
    berries: list[Berry] = []
    centres = np.sort(rng.uniform(0.12, 1.08, int(rng.integers(2, 6))))
    for cx in centres:
        group: list[Berry] = []
        for _ in range(int(rng.integers(1, 4))):
            for _try in range(20):
                r = float(rng.uniform(*BERRY_RADIUS))
                if not group:
                    pos = (float(cx), float(rng.uniform(*BERRY_Y)), float(rng.uniform(*BERRY_Z)))
                else:
                    a = group[0].pos
                    pos = (a[0] + float(rng.uniform(-0.05, 0.05)),
                           a[1] - float(rng.uniform(0.0, 0.09)),
                           a[2] + float(rng.uniform(-0.055, 0.055)))
                cand = Berry(f"b{len(berries) + len(group):02d}", pos, r,
                             float(rng.uniform(0.0, 1.0)), 0.0,
                             float(np.clip(rng.beta(2, 6), 0, 1)))
                clear = all(
                    abs(cand.pos[1] - o.pos[1]) >= cand.radius + o.radius + 0.004
                    or np.hypot(cand.pos[0] - o.pos[0], cand.pos[2] - o.pos[2])
                    >= cand.half_height + o.half_height + 0.004
                    for o in berries + group
                )
                if clear and 0.03 < pos[0] < 1.17 and 0.28 < pos[1] <= 0.44:
                    group.append(cand)
                    break
        berries += group
    return Scenario(scenario_id=f"T{seed}", seed=seed, berries=tuple(berries))


def training_scenario(seed: int) -> Scenario:
    if seed % 2:
        return cluster_scenario(seed)
    n = int(np.random.default_rng(seed).integers(4, 8))
    return generate(seed=seed, n_berries=n, scenario_id=f"T{seed}")


def render(seed: int) -> tuple[np.ndarray, np.ndarray, list[list[float]]]:
    """One scene: the frame, its depth, and a label per berry worth learning."""
    from . import scene
    from .camera import Intrinsics, camera_pose
    from .cell import MuJoCoCell

    sc = training_scenario(seed)
    cell = MuJoCoCell(sc, seed=seed)
    frame = cell.capture(scene.SURVEY_CAM, *SIZE)
    intr = Intrinsics.of(cell.model, scene.SURVEY_CAM, *SIZE)
    cam_pos, cam_mat = camera_pose(cell.model, cell.data, scene.SURVEY_CAM)
    labels = []
    for b in sc.berries:
        local = (cell.data.xpos[cell._berry[b.berry_id]] - cam_pos) @ cam_mat
        z = float(-local[2])
        u = intr.cx + intr.fx * local[0] / z
        v = intr.cy - intr.fy * local[1] / z
        visible = int((frame.seg == cell._berry_geom[b.berry_id]).sum())
        if visible < MIN_VISIBLE_PX or not (0 <= u < SIZE[0] and 0 <= v < SIZE[1]):
            continue
        labels.append([float(u), float(v), 2 * intr.fx * b.radius / z,
                       2 * intr.fy * b.half_height / z, b.ripeness, z])
    return frame.rgb, frame.depth.astype(np.float16), labels


def build_dataset(scenes: int, workers: int = 12) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    rgb = np.lib.format.open_memmap(DATA / "rgb.npy", "w+", np.uint8, (scenes, SIZE[1], SIZE[0], 3))
    depth = np.lib.format.open_memmap(DATA / "depth.npy", "w+", np.float16, (scenes, SIZE[1], SIZE[0]))
    labels = []
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(workers, mp_context=ctx) as pool:
        for i, (r, d, lab) in enumerate(pool.map(render, range(SEED0, SEED0 + scenes), chunksize=8)):
            rgb[i], depth[i] = r, d
            labels.append(lab)
            if (i + 1) % 400 == 0:
                print(f"  rendered {i + 1}/{scenes}", flush=True)
    rgb.flush(); depth.flush()
    (DATA / "labels.json").write_text(json.dumps(labels))


# ---- targets and loss ---------------------------------------------------------


def encode_targets(labels: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Labels to the network's output grid: target maps and a mask of centres."""
    h, w = SIZE[1] // STRIDE, SIZE[0] // STRIDE
    target = np.zeros((CHANNELS, h, w), np.float32)
    mask = np.zeros((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for u, v, bw, bh, ripeness, z in labels:
        cx, cy = min(int(u / STRIDE), w - 1), min(int(v / STRIDE), h - 1)
        sigma = max(0.8, min(bw, bh) / STRIDE / 6)
        target[0] = np.maximum(target[0], np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2)))
        target[1:, cy, cx] = (u / STRIDE - cx, v / STRIDE - cy, bw / SIZE_SCALE_PX,
                              bh / SIZE_SCALE_PX, ripeness, (z - DEPTH_REF_M) / DEPTH_SPAN_M)
        mask[cy, cx] = 1.0
    return target, mask


def loss_fn(out, target, mask):
    import torch
    import torch.nn.functional as F

    heat = torch.sigmoid(out[:, 0]).clamp(1e-4, 1 - 1e-4)
    gt = target[:, 0]
    pos = (gt == 1).float()
    # CenterNet's focal loss: cells near a centre are penalized less for firing.
    focal = -(pos * (1 - heat) ** 2 * torch.log(heat)
              + (1 - pos) * (1 - gt) ** 4 * heat**2 * torch.log(1 - heat)).sum()
    n = mask.sum().clamp(min=1)
    m = mask[:, None]
    reg = (F.l1_loss(out[:, 1:5] * m, target[:, 1:5] * m, reduction="sum")
           + 4 * F.l1_loss(torch.sigmoid(out[:, 5:6]) * m, target[:, 5:6] * m, reduction="sum")
           + 2 * F.l1_loss(out[:, 6:7] * m, target[:, 6:7] * m, reduction="sum"))
    return (focal + reg) / n


# ---- training -----------------------------------------------------------------


def evaluate(net, rgb, depth, labels, idx, device, threshold=0.35) -> dict:
    """Recall, precision and errors on held-out scenes, matched within 12 px."""
    import torch

    hits = misses = false = 0
    e_px, e_rip, e_size, e_z = [], [], [], []
    net.eval()
    with torch.no_grad():
        for i in idx:
            x = torch.from_numpy(encode_input(rgb[i], depth[i].astype(np.float32)))[None].to(device)
            found = decode(net(x)[0].cpu().numpy(), threshold)
            used = set()
            for u, v, bw, bh, ripeness, z in labels[i]:
                best = min(((np.hypot(f["u"] - u, f["v"] - v), j) for j, f in enumerate(found)
                            if j not in used), default=(1e9, -1))
                if best[0] > 12:
                    misses += 1
                    continue
                f = found[best[1]]; used.add(best[1]); hits += 1
                e_px.append(best[0]); e_rip.append(abs(f["ripeness"] - ripeness))
                e_size.append(abs(f["h"] - bh)); e_z.append(abs(f["z"] - z) * 1000)
            false += len(found) - len(used)
    return {"recall": hits / max(hits + misses, 1), "precision": hits / max(hits + false, 1),
            "centre_px": float(np.mean(e_px)), "ripeness_mae": float(np.mean(e_rip)),
            "height_px": float(np.mean(e_size)), "depth_mm": float(np.mean(e_z))}


def train(epochs: int, batch: int, val: int) -> dict:
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    rgb = np.load(DATA / "rgb.npy", mmap_mode="r")
    depth = np.load(DATA / "depth.npy", mmap_mode="r")
    labels = json.loads((DATA / "labels.json").read_text())
    n = len(labels)
    train_idx, val_idx = np.arange(n - val), np.arange(n - val, n)
    targets = [encode_targets(lab) for lab in labels]

    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    net = make_net().to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    steps = epochs * (len(train_idx) // batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=steps)
    t0 = time.time()
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(train_idx)
        total = 0.0
        for k in range(0, len(order) - batch + 1, batch):
            ids = np.sort(order[k : k + batch])
            x = np.stack([encode_input(rgb[i], depth[i].astype(np.float32)) for i in ids])
            # Lighting the network has not seen: per-channel gain and a lift.
            gain = rng.uniform(0.85, 1.15, (batch, 3, 1, 1)).astype(np.float32)
            x[:, :3] = np.clip(x[:, :3] * gain + rng.uniform(-0.04, 0.04, (batch, 1, 1, 1)), 0, 1)
            y = torch.from_numpy(np.stack([targets[i][0] for i in ids])).to(device)
            m = torch.from_numpy(np.stack([targets[i][1] for i in ids])).to(device)
            loss = loss_fn(net(torch.from_numpy(x).to(device)), y, m)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            total += float(loss)
        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            stats = evaluate(net, rgb, depth, labels, val_idx, device)
            print(f"epoch {epoch + 1:>3}/{epochs}  loss {total / (len(order) // batch):.3f}  "
                  f"recall {stats['recall']:.3f}  precision {stats['precision']:.3f}  "
                  f"centre {stats['centre_px']:.2f}px  ripeness {stats['ripeness_mae']:.3f}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    torch.save({k: v.cpu() for k, v in net.state_dict().items()}, WEIGHTS)
    stats = evaluate(net, rgb, depth, labels, val_idx, device)
    stats.update(scenes=n, val_scenes=val, epochs=epochs, seconds=round(time.time() - t0),
                 berries=sum(len(lab) for lab in labels),
                 parameters=sum(p.numel() for p in net.parameters()))
    (WEIGHTS.parent / "berry_detector.json").write_text(json.dumps(stats, indent=1))
    return stats


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m harvestbench.train_detector")
    p.add_argument("--scenes", type=int, default=2400)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--val", type=int, default=200, help="scenes held out of training")
    p.add_argument("--reuse-data", action="store_true", help="train on the dataset already rendered")
    args = p.parse_args(argv)
    if not (args.reuse_data and (DATA / "labels.json").exists()):
        print(f"rendering {args.scenes} scenes", flush=True)
        build_dataset(args.scenes)
    stats = train(args.epochs, args.batch, args.val)
    print(json.dumps(stats, indent=1))
    print(f"wrote {WEIGHTS}")


if __name__ == "__main__":
    main()
