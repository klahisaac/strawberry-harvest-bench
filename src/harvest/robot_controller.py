"""How the robot picks a strawberry: which berry, and the path its cutter takes.

This is the robot's decision-making, and the only file to change to change it.
The simulator (reproduce_scene.py) gives it the berries the camera found and
moves the cutter along the waypoints it returns.

World frame, in metres: x to the right, y away from the robot, z up.
"""

import dataclasses

import numpy as np

CUT_ABOVE_TOP = 0.012  # the stem is cut this far above the top of the fruit
APPROACH_DISTANCE = 0.12  # the cutter lines up this far in front of the stem


@dataclasses.dataclass
class Berry:
    """A berry as the camera sees it."""

    center: np.ndarray  # metres, world frame
    radius: float  # half the width, metres
    ripe: bool

    @property
    def top(self) -> np.ndarray:
        """Where the stem leaves the fruit. A strawberry is about 1.4 times taller than wide."""
        return self.center + [0.0, 0.0, 1.4 * self.radius]


@dataclasses.dataclass
class Waypoint:
    """A place for the cutter's tip, and the way the cutter points there."""

    position: np.ndarray
    direction: np.ndarray
    cut: bool = False  # close the cutter here


def choose_target(berries: list[Berry], camera_axis: np.ndarray) -> Berry | None:
    """The ripe berry nearest the camera's line of sight: the robot stopped in front of it."""
    ripe = [b for b in berries if b.ripe]
    if not ripe:
        return None
    return min(ripe, key=lambda b: np.linalg.norm((b.center - camera_axis)[[0, 2]]))


def plan(target: Berry, berries: list[Berry]) -> list[Waypoint]:
    """Line up in front of the stem, go straight in, cut, and back out."""
    cut_point = target.top + [0.0, 0.0, CUT_ABOVE_TOP]
    forward = np.array([0.0, 1.0, 0.0])  # straight in, away from the robot
    start = cut_point - forward * APPROACH_DISTANCE
    return [
        Waypoint(start, forward),
        Waypoint(cut_point, forward, cut=True),
        Waypoint(start, forward),
    ]
