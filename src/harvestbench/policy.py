"""Which berries to go for, in what order.

This is the baseline, and it is deliberately rough. It runs, which is the point
— the bench needs something to measure before it can show an improvement. Every
shortcut below is a metric waiting to move:

  * A hardcoded ripeness threshold on a noisy estimate, with no allowance for
    how uncertain that estimate is. Produces false picks and missed ripe fruit.
  * Confidence and occlusion are read and then ignored, so the arm spends full
    cycles reaching for berries it cannot get to.
  * One attempt per berry. No retry from another angle.
  * Left to right along the gutter, with no account of rail travel.

The approach direction is the cell's business, and it is head-on there for the
same reason. See DESIGN.md, "Build it as a codebase that was inherited".
"""

from dataclasses import dataclass

from .cell import DetectedBerry
from .scenario import RIPE_MIN


@dataclass
class BaselinePolicy:
    name: str = "baseline"
    ripeness_threshold: float = RIPE_MIN

    def choose(self, detections: list[DetectedBerry]) -> list[DetectedBerry]:
        ripe = [d for d in detections if d.ripeness >= self.ripeness_threshold]
        return sorted(ripe, key=lambda d: d.pos[0])
