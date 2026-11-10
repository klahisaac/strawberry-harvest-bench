"""What a gutter of plants looks like, generated from a seed.

A Scenario is the full ground truth of one harvest situation: where every berry
is, how ripe it is, which way its peduncle runs. Perception never sees this
directly — it only sees what the simulated camera reports. This is the same
split lab-robot draws between its Oracle and its planner.
"""

from dataclasses import dataclass
import zlib

import numpy as np

# Gutter geometry (metres). The arm approaches from -y.
GUTTER_X = (0.05, 1.15)
GUTTER_FACE_Y = 0.45
GUTTER_TOP_Z = 0.90

# Where berries hang relative to the gutter face.
BERRY_Y = (0.38, 0.44)
BERRY_Z = (0.74, 0.84)
BERRY_RADIUS = (0.013, 0.022)
BERRY_MASS = 0.022
# A strawberry is taller than it is wide. The colliding body is an ellipsoid of
# (radius, radius, radius * this), which is what sets where the cut point sits.
BERRY_HEIGHT_RATIO = 1.35

# A berry is worth picking at or above RIPE_MIN and below OVERRIPE.
RIPE_MIN = 0.60
OVERRIPE = 0.95


@dataclass(frozen=True)
class Berry:
    berry_id: str
    pos: tuple[float, float, float]
    radius: float
    ripeness: float
    peduncle_yaw: float  # radians; 0 means the stem runs along +y
    occlusion: float  # 0 clear, 1 fully hidden by leaves

    @property
    def should_pick(self) -> bool:
        """Ground truth: the correct decision for this berry."""
        return RIPE_MIN <= self.ripeness < OVERRIPE

    @property
    def half_height(self) -> float:
        return self.radius * BERRY_HEIGHT_RATIO

    @property
    def cut_point(self) -> tuple[float, float, float]:
        """Where the cutter has to be: just above the berry, on the peduncle."""
        x, y, z = self.pos
        return (x, y, z + self.half_height + 0.012)

    def rng(self, seed: int) -> np.random.Generator:
        """A stream of its own, so one berry behaves the same across runs."""
        return np.random.default_rng(zlib.crc32(self.berry_id.encode()) + seed)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    berries: tuple[Berry, ...]

    @property
    def pickable(self) -> tuple[Berry, ...]:
        return tuple(b for b in self.berries if b.should_pick)


def generate(seed: int, n_berries: int = 6, scenario_id: str | None = None) -> Scenario:
    """A gutter with n_berries spaced along it, ripeness and pose randomized."""
    rng = np.random.default_rng(seed)
    lo, hi = GUTTER_X
    # Even spacing with jitter, so berries do not overlap but are not on a grid.
    slots = np.linspace(lo + 0.06, hi - 0.06, n_berries)
    jitter = rng.uniform(-0.02, 0.02, n_berries)

    berries = []
    for i, (x, dx) in enumerate(zip(slots, jitter)):
        berries.append(
            Berry(
                berry_id=f"b{i:02d}",
                pos=(
                    float(x + dx),
                    float(rng.uniform(*BERRY_Y)),
                    float(rng.uniform(*BERRY_Z)),
                ),
                radius=float(rng.uniform(*BERRY_RADIUS)),
                # Skewed so most berries are ripe but some are not: the policy
                # has to decide, not just reach.
                ripeness=float(np.clip(rng.beta(6, 2), 0, 1)),
                peduncle_yaw=float(rng.uniform(-0.5, 0.5)),
                occlusion=float(np.clip(rng.beta(2, 6), 0, 1)),
            )
        )
    return Scenario(
        scenario_id=scenario_id or f"S{seed:04d}",
        seed=seed,
        berries=tuple(berries),
    )
