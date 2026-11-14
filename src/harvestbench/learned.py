"""A learned berry detector: one small network in place of the colour threshold.

The colour detector finds what is saturated and not leaf-green, and measures
whatever it can see. That is its weakness: a berry with its top behind a leaf,
or behind another berry, reads as a shorter berry, and the cut point lands in
the fruit. This detector is trained to report each berry whole — centre, full
width and height, ripeness and distance — from the part of it that shows.

It is a CenterNet-style head on a small convolutional body. For every cell of
a stride-4 grid it predicts whether a berry's centre is there and, if so, the
sub-cell offset, the berry's full size in pixels, its ripeness and its depth.
Input is the survey frame as RGB plus depth.

Training data costs nothing to label: the simulator knows where every berry
is, how big and how ripe, whatever is in front of it. See train_detector.py.
The tier scenarios and the demo's photographed cluster are never trained on.

PyTorch is imported only when this detector is used, so the bench runs
without it; `--detector colour` needs nothing but NumPy and SciPy.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .camera import Intrinsics, pixel_to_world
from .cell import DetectedBerry

WEIGHTS = Path(__file__).with_name("weights") / "berry_detector.pt"
STRIDE = 4
CHANNELS = 7  # centre heat, dx, dy, width, height, ripeness, depth
DEPTH_REF_M = 0.9  # roughly where the fruit hangs from the survey camera
DEPTH_SPAN_M = 0.3
SIZE_SCALE_PX = 32.0  # sizes are regressed in units of this many pixels
SURVEY_CAMERA = "survey_cam"


def make_net():
    """The network. Built here so importing this module does not need torch."""
    from torch import nn

    def conv(cin, cout, stride=1, dilation=1):
        return nn.Sequential(
            nn.Conv2d(cin, cout, 3, stride, padding=dilation, dilation=dilation, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
        )

    class Block(nn.Module):
        def __init__(self, ch, dilation):
            super().__init__()
            self.a, self.b = conv(ch, ch, dilation=dilation), conv(ch, ch)

        def forward(self, x):
            return x + self.b(self.a(x))

    class BerryNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.stem = nn.Sequential(conv(4, 32, stride=2), conv(32, 64, stride=2))
            # Dilation widens the view without losing resolution: a berry is
            # about 25 px across, and a leaf over it a good deal more.
            self.body = nn.Sequential(*(Block(64, d) for d in (1, 2, 4, 2, 1)))
            self.head = nn.Sequential(conv(64, 64), nn.Conv2d(64, CHANNELS, 1))
            # Start out predicting "no berry here" almost everywhere.
            nn.init.constant_(self.head[-1].bias[:1], -2.2)

        def forward(self, x):
            return self.head(self.body(self.stem(x)))

    return BerryNet()


def encode_input(rgb: np.ndarray, depth: np.ndarray) -> np.ndarray:
    """A frame as the (4, h, w) float array the network reads."""
    d = np.where(np.isfinite(depth), depth, DEPTH_REF_M + 2 * DEPTH_SPAN_M)
    d = np.clip((d - DEPTH_REF_M) / DEPTH_SPAN_M, -2.0, 2.0)
    return np.concatenate(
        [rgb.transpose(2, 0, 1).astype(np.float32) / 255.0, d[None].astype(np.float32)]
    )


@dataclass
class LearnedDetector:
    """Berries from the survey frame, by a trained network.

    Only the survey camera's frame goes through the network. The check on the
    fruit in the tray, from the wrist camera, stays with the colour detector:
    one berry alone, close and lit, is the easy case, and the network was not
    trained on that view.
    """

    name: str = "learned"
    weights: Path = WEIGHTS
    threshold: float = 0.35
    _net: object = field(default=None, repr=False)
    _colour: object = field(default=None, repr=False)

    def _load(self):
        if self._net is None:
            try:
                import torch
            except ImportError as exc:
                raise SystemExit(
                    "--detector learned needs PyTorch: run `uv sync --group ml`"
                ) from exc
            if not self.weights.exists():
                raise SystemExit(
                    f"no trained weights at {self.weights}: run "
                    "`uv run --group ml python -m harvestbench.train_detector`"
                )
            # One thread, on the CPU: the suite runs a dozen of these side by
            # side, and a run has to give the same numbers every time.
            torch.set_num_threads(1)
            net = make_net()
            net.load_state_dict(torch.load(self.weights, map_location="cpu"))
            self._net = net.eval()
        return self._net

    def detect(
        self, frame, intr: Intrinsics, cam_pos: np.ndarray, cam_mat: np.ndarray
    ) -> list[DetectedBerry]:
        if frame.camera != SURVEY_CAMERA:
            if self._colour is None:
                from .perception import ColorThresholdDetector

                self._colour = ColorThresholdDetector()
            return self._colour.detect(frame, intr, cam_pos, cam_mat)
        import torch

        net = self._load()
        with torch.no_grad():
            out = net(torch.from_numpy(encode_input(frame.rgb, frame.depth))[None])[0].numpy()
        found = decode(out, self.threshold)
        berries = []
        for i, d in enumerate(sorted(found, key=lambda d: d["u"])):
            pos = pixel_to_world(
                np.array(d["u"]), np.array(d["v"]), np.array(d["z"]), intr, cam_pos, cam_mat
            )
            berries.append(
                DetectedBerry(
                    berry_id=f"d{i:02d}",
                    pos=tuple(float(v) for v in pos),
                    radius=float(d["w"] / 2 * d["z"] / intr.fx),
                    half_height=float(d["h"] / 2 * d["z"] / intr.fy),
                    ripeness=float(d["ripeness"]),
                    occlusion=0.0,
                    confidence=float(d["score"]),
                )
            )
        return berries


def decode(out: np.ndarray, threshold: float) -> list[dict]:
    """Network output (7, h/4, w/4) to berries in full-resolution pixels."""
    heat = 1.0 / (1.0 + np.exp(-out[0]))
    # A peak is a cell that beats its eight neighbours.
    padded = np.pad(heat, 1, constant_values=0.0)
    neighbours = np.max(
        [padded[1 + dy : 1 + dy + heat.shape[0], 1 + dx : 1 + dx + heat.shape[1]]
         for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)],
        axis=0,
    )
    ys, xs = np.nonzero((heat >= neighbours) & (heat > threshold))
    found = []
    for y, x in zip(ys, xs):
        found.append({
            "score": float(heat[y, x]),
            "u": float((x + out[1, y, x]) * STRIDE),
            "v": float((y + out[2, y, x]) * STRIDE),
            "w": float(max(out[3, y, x], 0.05) * SIZE_SCALE_PX),
            "h": float(max(out[4, y, x], 0.05) * SIZE_SCALE_PX),
            "ripeness": float(1.0 / (1.0 + np.exp(-out[5, y, x]))),
            "z": float(DEPTH_REF_M + out[6, y, x] * DEPTH_SPAN_M),
        })
    return found
