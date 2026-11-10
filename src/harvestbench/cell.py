"""The harvest cell: one interface, a MuJoCo backend, and a stub for hardware.

Control code talks to `HarvestCell` and never to MuJoCo directly, so the same
policy runs against the simulator and, later, against a real machine. This is
lab-robot's `VirtualRobot` boundary in a different domain.

Failure modes come out of the physics rather than a table. A berry is caught
because it landed on the tray; a stem tears because the cutter pushed the berry
while it was still attached; a neighbour is knocked because something touched
it. Nothing is scored by fiat.
"""

from dataclasses import dataclass, field
from typing import Protocol

import mujoco
import numpy as np

from . import scene
from .ik import ArmIK
from .camera import CameraRig, Intrinsics, camera_pose
from .scenario import Berry, Scenario
from .telemetry import Telemetry

# Damage is judged by contact force, not displacement.
#
# Displacement was the obvious proxy and it was wrong. The weld holding a berry
# has to be stiff enough that gravity does not sag it, and at that stiffness a
# berry pushed by the arm barely moves — under half a millimetre — so a berry in
# the way reads as a wall rather than as damage. Force is the quantity that
# actually distinguishes "brushed past" from "crushed", and it does not depend
# on how compliant the stem model happens to be.
STEM_TEAR_N = 6.0  # force on the target berry while still attached
KNOCK_N = 1.5  # force on a berry that is not the target
# How close the cutter must be to a stem for the blades to take it (metres).
CUT_REACH_M = 0.030
# Standoff before the final approach (metres, along -y).
STANDOFF_M = 0.10
# Cutter placement tolerance for "reached" (metres).
REACH_TOL_M = 0.010

# Placing. Over the cup the tray's floor opens like a trapdoor and the berry
# drops straight down. A tipping pour was tried first and could not be made
# accurate: the berry slid five centimetres across the tray, left it at about
# a third of a metre per second, and hopped the cup walls. Dropping it removes
# the sideways speed, so where it lands depends on where it sat on the tray,
# and how hard it lands depends on one thing — the height it fell from.
#
# The real machine places with a gripper. This end effector keeps its catch
# tray because the cut, the catch and every force threshold were calibrated
# against it, and a gripper would start all of that over.
#
# The baseline releases high, with room to spare over the cups. That is safe
# for the tray and rough on the fruit, which is the point of a baseline.
RELEASE_HEIGHT_M = 0.045  # tray floor above the cup floor when it opens
HOVER_CLEAR_M = 0.040  # extra height while moving over the punnet
# Where a carried berry sits: against the tray lip, which it rolls to as the
# arm decelerates. Every traced carry ended there. The inner face of the lip
# is this far from the tray centre, so a berry of radius r rests at this
# minus r — which the robot can work out from its own size estimate.
LIP_FACE_M = 0.055
# Landing faster than this bruises the fruit. It is the speed of a free fall
# from 3 cm, and like the other damage thresholds it is a guess, not a
# measurement: strawberries bruise easily, but this number is not from a lab.
BRUISE_SPEED_M_S = 0.77

# Carrying fruit. A position servo handed a far-off target lunges at it, and
# a berry on an open tray goes flying. With fruit aboard the arm follows a
# minimum-jerk trajectory instead, paced by these speeds.
CARRY_RAIL_M_S = 0.40
CARRY_JOINT_RAD_S = 0.80
CARRY_MIN_S = 0.6
# With fruit aboard the arm pulls back to this distance from the rail before
# the carriage moves, so the tray travels well clear of the fruit still
# hanging, and from there goes straight to the punnet.
TRANSIT_Y = 0.20

# Joint order is scene.ARM_JOINTS: rail, yaw, shoulder, elbow, wrist.
RAIL, YAW, SHOULDER, ELBOW, WRIST = range(5)


def level_tray(q: np.ndarray) -> None:
    """Keep the catch tray horizontal.

    All three hinges turn about the same local x axis, so the wrist frame's
    pitch is just their sum. Cancelling it leaves the tray level, which is what
    lets a cut berry land in it instead of rolling off.
    """
    q[WRIST] = -(q[SHOULDER] + q[ELBOW])


# Where the arm waits: folded back, cutter 28 cm out from the rail at the
# height of the fruit, tray level. Clear of the gutter and the fruit wherever
# the carriage is.
#
# The old home, [0, 0, 0.55, -1.15, 0.60], put the tray under the gutter's
# footprint at the height of its underside. At rail 0 that is just past the
# gutter's end, so the pose itself looked fine — but the arm takes that shape
# long before the carriage gets back, and drove the tray up under the gutter
# and along it. 127 of 203 parks never arrived, and the next approach started
# from wherever the arm had jammed.
HOME_Q = np.array([0.0, 0.0, 1.05, -2.25, 1.20])



@dataclass
class SensorConfig:
    """A cheap stand-in for the camera, fitted to what the camera actually does.

    This is not an idealization and must not be read as one. It was originally
    a guess, and the guess was wrong in both directions: it dropped a berry with
    probability `0.85 x occlusion` on a nominal occlusion value that mostly
    corresponds to nothing, discarding a fifth of the ripe fruit for no physical
    reason, while being too generous about where the rest of it was.

    The numbers below come from 150 berries read by `ColorThresholdDetector`
    through the survey camera, bucketed by measured occlusion:

        occlusion   detected   position error   ripeness error
        none          100%         6.4 mm           0.015
        light         100%         6.0 mm           0.009
        partial       100%        11.3 mm           0.013
        heavy          89%        18.1 mm           0.018

    Position error is the magnitude of a 3D offset, so the per-axis sigma is
    that divided by about 1.6.
    """

    pos_noise_m: float = 0.004
    ripeness_noise: float = 0.018
    # Error grows with occlusion: ~4 mm per axis clear, ~11 mm when mostly
    # hidden, which is a slope of roughly 9 mm per unit of occlusion.
    occlusion_pos_penalty_m: float = 0.009
    # Detection does not degrade gradually. It holds at 100% until a berry is
    # more than about 60% hidden, and only then starts to fail.
    dropout_onset: float = 0.60
    dropout_rate: float = 0.30

# A sensor that misreports nothing. Useful for isolating a failure to the
# mechanics, and named rather than written out positionally so that adding a
# field cannot silently turn it into something else.
PERFECT_SENSOR = SensorConfig(
    pos_noise_m=0.0, ripeness_noise=0.0, occlusion_pos_penalty_m=0.0, dropout_rate=0.0
)


@dataclass(frozen=True)
class DetectedBerry:
    """What the robot believes about a berry.

    In this phase the fields come from ground truth plus noise. When a trained
    perception model replaces that, it produces this same type, so the policy
    does not change.
    """

    berry_id: str
    pos: tuple[float, float, float]
    radius: float
    half_height: float
    ripeness: float
    occlusion: float
    confidence: float

    @property
    def cut_point(self) -> np.ndarray:
        """Where to put the cutter: a stem's width above the estimated top.

        This reads `half_height`, not `radius`. A strawberry is taller than it
        is wide, and aiming at `radius` puts the cutter several millimetres low
        — into the fruit — which the bench scores as a torn stem.
        """
        x, y, z = self.pos
        return np.array([x, y, z + self.half_height + 0.012])


def _detection_record(d: DetectedBerry) -> dict:
    return {
        "id": d.berry_id,
        "pos": [round(float(v), 4) for v in d.pos],
        "radius": round(float(d.radius), 4),
        "half_height": round(float(d.half_height), 4),
        "ripeness": round(float(d.ripeness), 3),
        "confidence": round(float(d.confidence), 3),
    }


@dataclass
class PickResult:
    berry_id: str
    reached: bool = False
    cut: bool = False
    caught: bool = False
    dropped: bool = False
    stem_torn: bool = False
    knocked: tuple[str, ...] = ()
    # What the detection was called. With a camera this is a made-up label.
    cut_berry_id: str | None = None  # the berry actually cut, or pressed
    attempts: int = 0
    ik_error_m: float = 0.0
    duration_s: float = 0.0
    peak_force_n: float = 0.0  # on the target, while still attached
    # Ripeness re-read from the tray after the cut, where the fruit is close,
    # lit and unoccluded. None when nothing was there to look at.
    tray_ripeness: float | None = None
    # The place step, after a catch. A cup index is a position in the punnet's
    # packing order; landed_cell is where the berry actually came to rest.
    place_cell: int | None = None
    landed_cell: int | None = None
    spilled: bool = False  # ended up somewhere other than the punnet
    impact_speed_m_s: float | None = None  # on first landing, None if never
    note: str = ""

    @property
    def packed(self) -> bool:
        """Harvested and in the punnet: the only pick that is worth anything."""
        return self.caught and self.landed_cell is not None

    @property
    def placed(self) -> bool:
        """In the cup it was meant for."""
        return self.packed and self.landed_cell == self.place_cell

    @property
    def bruised(self) -> bool:
        return (
            self.impact_speed_m_s is not None
            and self.impact_speed_m_s > BRUISE_SPEED_M_S
        )

    @property
    def outcome(self) -> str:
        if self.caught and self.spilled:
            return "spilled"
        if self.caught:
            return "picked"
        if self.stem_torn:
            return "stem_torn"
        if self.dropped:
            return "dropped"
        if not self.reached:
            return "unreachable"
        return "missed"

    @property
    def damaged(self) -> bool:
        return self.stem_torn or bool(self.knocked) or self.bruised


class HarvestCell(Protocol):
    def reset(self) -> None: ...
    def observe(self) -> list[DetectedBerry]: ...
    def pick(self, target: DetectedBerry) -> PickResult: ...
    def park(self) -> None: ...
    @property
    def time(self) -> float: ...


@dataclass
class MuJoCoCell:
    scenario: Scenario
    seed: int = 0
    sensor: SensorConfig = field(default_factory=SensorConfig)
    telemetry: Telemetry = field(default_factory=Telemetry)
    # Trajectory sampling, for watching a run. 0 keeps it off, which is what the
    # scenario suite wants: frames are only needed when a human will watch.
    frame_hz: float = 0.0
    # None reads the simulator's ground truth with noise added. Anything else
    # has to work from the camera.
    detector: object | None = None
    camera_size: tuple[int, int] = (640, 480)
    # Leaves to build instead of the generated ones, for a scene laid out by
    # hand rather than drawn from a seed.
    leaf_boxes: list[dict] | None = None
    mjcf: str = field(init=False)

    def __post_init__(self):
        self.mjcf = scene.build(self.scenario, self.leaf_boxes)
        self.model = mujoco.MjModel.from_xml_string(self.mjcf)
        self.data = mujoco.MjData(self.model)
        self.ik = ArmIK(
            self.model,
            scene.CUTTER_SITE,
            scene.ARM_JOINTS,
            free=(RAIL, YAW, SHOULDER, ELBOW),
            couple=level_tray,
        )
        # The arm solved with yaw held at zero, for placing. A yawed tray puts
        # the berry off to one side of where the tray centre was aimed; the
        # rail lines the punnet's columns up instead.
        self.place_ik = ArmIK(
            self.model,
            scene.CUTTER_SITE,
            scene.ARM_JOINTS,
            free=(RAIL, SHOULDER, ELBOW),
            couple=level_tray,
        )
        self._tray_parts = tuple(
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)
            for name in (scene.TRAY_GEOM, "tray_lip")
        )
        self._tray_collide = {
            g: (int(self.model.geom_contype[g]), int(self.model.geom_conaffinity[g]))
            for g in self._tray_parts
        }
        self._cells = scene.punnet_cells(self.scenario)
        self._punnet_geoms = {
            g
            for g in range(self.model.ngeom)
            if (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, g) or "").startswith(
                scene.PUNNET_GEOM_PREFIX
            )
        }
        self._floor = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self._cutter = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, scene.CUTTER_SITE)
        self._tray = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, scene.TRAY_GEOM)
        self._berry = {
            b.berry_id: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, b.berry_id)
            for b in self.scenario.berries
        }
        self._cut_site = {
            b.berry_id: mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_SITE, f"{b.berry_id}_cut"
            )
            for b in self.scenario.berries
        }
        self._stem = {
            b.berry_id: mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_EQUALITY, f"{b.berry_id}_stem"
            )
            for b in self.scenario.berries
        }
        self._by_id = {b.berry_id: b for b in self.scenario.berries}
        self._body_berry = {body: bid for bid, body in self._berry.items()}
        # Geoms that count as the arm striking something. The tray belongs to the
        # wrist body but is excluded on purpose: a berry resting in it after the
        # cut is a successful catch, and counting its weight as a strike put a
        # clean pick within 0.5 N of the stem-tear threshold.
        arm_bodies = {
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            for name in ("carriage", "yaw_link", "upper", "fore", "wrist")
        }
        catchers = {
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)
            for name in (scene.TRAY_GEOM, "tray_lip")
        }
        self._strike_geoms = {
            g for g in range(self.model.ngeom) if self.model.geom_bodyid[g] in arm_bodies
        } - catchers
        self._cf = np.zeros(6)
        self._force: dict[str, float] = {}
        self._catchers = catchers
        # The berry being carried to the punnet, and how fast it was moving the
        # first time it touched anything other than the tray.
        self._carrying: str | None = None
        self._impact: float | None = None
        self._speed_before = 0.0
        # The points a recorded frame keeps of the arm, so whatever draws it
        # never needs forward kinematics of its own.
        self._link_ids = {
            name: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, body)
            # carriage -> elbow -> wrist -> cutter is the arm as a polyline. The
            # shoulder sits at the carriage origin, so it adds nothing.
            for name, body in (
                ("carriage", "carriage"),
                ("elbow", "fore"),
                ("wrist", "wrist"),
            )
        }
        self.frames: list[dict] = []
        self._phase = "idle"
        self._next_frame_t = 0.0
        self._rig: CameraRig | None = None
        self._occlusion: dict[str, float] | None = None
        self.survey_frame = None
        self._leaf_geoms = tuple(
            name
            for g in range(self.model.ngeom)
            if (name := mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, g))
            and name.endswith("_leafgeom")
        )
        self._berry_geom = {
            b.berry_id: mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_GEOM, f"{b.berry_id}_geom"
            )
            for b in self.scenario.berries
        }
        self.reset()

    # ---- camera -----------------------------------------------------------

    def rig(self, width: int = 320, height: int = 240) -> CameraRig:
        """The renderer, built on first use. An OpenGL context is not cheap."""
        if self._rig is None or (self._rig.width, self._rig.height) != (width, height):
            if self._rig is not None:
                self._rig.close()
            self._rig = CameraRig(self.model, width, height)
        return self._rig

    def capture(self, camera: str = scene.SURVEY_CAM, width: int = 320, height: int = 240):
        return self.rig(width, height).capture(self.data, camera)

    @property
    def occlusion(self) -> dict[str, float]:
        """Measured occlusion, computed once and reused.

        Both the metric buckets and the cheap sensor model read this, so they
        cannot disagree about how hidden a berry is.
        """
        if self._occlusion is None:
            self._occlusion = self.measure_occlusion()
        return self._occlusion

    def measure_occlusion(
        self, camera: str = scene.SURVEY_CAM, width: int = 320, height: int = 240
    ) -> dict[str, float]:
        """How hidden each berry actually is from the current viewpoint.

        The scenario carries a nominal occlusion, but that number only decides
        whether a leaf is generated and how big it is. Below the leaf threshold
        it corresponds to nothing in the world at all. This is the real figure:
        pixels visible now, against pixels visible with the leaves taken away.
        """
        rig = self.rig(width, height)
        # The arm is out of both renders. It does block the view sometimes,
        # but that is a different thing from foliage and mixing the two would
        # make the bucket depend on where the arm happened to be parked.
        arm = (scene.ARM_GEOM_GROUP,)
        with_leaves = rig.capture(self.data, camera, hide_groups=arm)
        without = rig.capture(
            self.data, camera, hide=self._leaf_geoms, hide_groups=arm
        )
        out = {}
        for bid, gid in self._berry_geom.items():
            full = int((without.seg == gid).sum())
            if full == 0:
                out[bid] = 1.0  # out of frame entirely
                continue
            out[bid] = float(1.0 - (with_leaves.seg == gid).sum() / full)
        return out

    # ---- state -------------------------------------------------------------

    def reset(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.ik.qadr] = HOME_Q
        self.data.ctrl[:] = HOME_Q
        mujoco.mj_forward(self.model, self.data)
        self._settle(0.2)
        self._home_pos = {bid: self.data.xpos[i].copy() for bid, i in self._berry.items()}
        self._harvested: set[str] = set()
        self._next_cell = 0
        self.telemetry.event(self.time, "run.started", self.scenario.scenario_id,
                             berries=len(self.scenario.berries))

    @property
    def time(self) -> float:
        return float(self.data.time)

    @property
    def q(self) -> np.ndarray:
        return self.data.qpos[self.ik.qadr].copy()

    def _settle(self, seconds: float) -> None:
        for _ in range(int(seconds / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)
            self._scan_contacts()
            self._maybe_frame()

    def _maybe_frame(self) -> None:
        """Sample the arm and fruit at frame_hz."""
        if not self.frame_hz or self.data.time < self._next_frame_t:
            return
        self._next_frame_t = self.data.time + 1.0 / self.frame_hz

        def xyz(v) -> list[float]:
            return [round(float(x), 4) for x in v]

        arm = {name: xyz(self.data.xpos[i]) for name, i in self._link_ids.items()}
        arm["cutter"] = xyz(self.data.site_xpos[self._cutter])
        arm["tray"] = xyz(self.data.geom_xpos[self._tray])
        self.frames.append(
            {
                "t": round(float(self.data.time), 3),
                "phase": self._phase,
                "arm": arm,
                "berries": {bid: xyz(self.data.xpos[i]) for bid, i in self._berry.items()},
            }
        )

    def _scan_contacts(self) -> None:
        """Track the hardest the arm has pressed on each berry this attempt."""
        if self._carrying is not None:
            self._watch_landing()
        for i in range(self.data.ncon):
            con = self.data.contact[i]
            if con.geom1 in self._strike_geoms:
                berry = self._body_berry.get(self.model.geom_bodyid[con.geom2])
            elif con.geom2 in self._strike_geoms:
                berry = self._body_berry.get(self.model.geom_bodyid[con.geom1])
            else:
                continue  # berry in the tray, or the arm against a leaf
            # A cut berry rides along in the tray and leans on the arm. That is
            # not the arm striking fruit, so stop counting once it is harvested.
            if berry is None or berry in self._harvested:
                continue
            mujoco.mj_contactForce(self.model, self.data, i, self._cf)
            force = float(np.linalg.norm(self._cf[:3]))
            if force > self._force.get(berry, 0.0):
                self._force[berry] = force

    def _watch_landing(self) -> None:
        """Record the hardest the carried berry hits anything on the way down.

        The hardest, not the first: a berry slightly off centre grazes the rim
        of its cup before it reaches the floor, and that glancing touch is far
        gentler than the landing that does the bruising.

        Speed, not contact force, for the same reason damage on the plant is
        judged by force rather than displacement: it is the quantity that does
        not depend on how soft the simulator's contacts happen to be. A cup, a
        wall, the floor or another berry counts as landing. The tray and the
        rest of the arm do not: a carried berry leans on the cutter head, and
        counting that would record a gentle landing before the real one.
        """
        body = self._berry[self._carrying]
        dof = self.model.body_dofadr[body]
        # The speed going into this step. By the time a step has run, the
        # contact it found has already pushed back, so reading the speed after
        # the step that touched down under-reads the landing by a third.
        before = self._speed_before
        self._speed_before = float(np.linalg.norm(self.data.qvel[dof : dof + 3]))
        for i in range(self.data.ncon):
            con = self.data.contact[i]
            b1 = self.model.geom_bodyid[con.geom1]
            b2 = self.model.geom_bodyid[con.geom2]
            if body not in (b1, b2):
                continue
            other = con.geom2 if b1 == body else con.geom1
            if other in self._catchers or other in self._strike_geoms:
                continue
            self._impact = max(self._impact or 0.0, before)
            return

    # ---- observation -------------------------------------------------------

    def observe(self) -> list[DetectedBerry]:
        """What the robot believes is on the gutter.

        Two paths. With a `detector` set, a camera frame is rendered and the
        detector reads it — berry ids are then whatever the detector made up,
        because nothing in a picture carries an identity. Without one, this
        falls back to ground truth plus noise, which is faster and is the
        idealized comparison: how much worse is reading pixels than being told?
        """
        if self.detector is not None:
            frame = self.capture(scene.SURVEY_CAM, *self.camera_size)
            self.survey_frame = frame
            intr = Intrinsics.of(self.model, scene.SURVEY_CAM, *self.camera_size)
            pos, mat = camera_pose(self.model, self.data, scene.SURVEY_CAM)
            found = self.detector.detect(frame, intr, pos, mat)
            self.telemetry.event(self.time, "perception.frame",
                                 f"{len(found)} candidates",
                                 detector=self.detector.name,
                                 detected=[d.berry_id for d in found],
                                 # What perception reported, in full. A field
                                 # log needs it to rebuild the scene later.
                                 detections=[_detection_record(d) for d in found])
            return found
        # The cheap path still records the picture, so either path leaves the
        # same scene behind to look at.
        self.survey_frame = self.capture(scene.SURVEY_CAM, *self.camera_size)
        return self._observe_oracle()

    def _observe_oracle(self) -> list[DetectedBerry]:
        """Noisy view of the gutter. Occluded berries are worse, or absent."""
        cfg = self.sensor
        measured = self.occlusion
        out = []
        for b in self.scenario.berries:
            rng = b.rng(self.seed)
            occ = measured.get(b.berry_id, b.occlusion)
            # Fitted to the camera: nothing is missed until a berry is mostly
            # hidden, and the nominal occlusion is not what decides it.
            hidden = max(0.0, (occ - cfg.dropout_onset) / (1 - cfg.dropout_onset))
            if rng.random() < cfg.dropout_rate * hidden:
                continue
            spread = cfg.pos_noise_m + cfg.occlusion_pos_penalty_m * occ
            pos = np.array(b.pos) + rng.normal(0, spread, 3)
            out.append(
                DetectedBerry(
                    berry_id=b.berry_id,
                    pos=tuple(float(v) for v in pos),
                    radius=float(b.radius + rng.normal(0, 0.002)),
                    half_height=float(b.half_height + rng.normal(0, 0.003)),
                    ripeness=float(np.clip(b.ripeness + rng.normal(0, cfg.ripeness_noise), 0, 1)),
                    occlusion=float(occ),
                    confidence=float(np.clip(1.0 - b.occlusion + rng.normal(0, 0.05), 0, 1)),
                )
            )
        self.telemetry.event(self.time, "perception.frame", f"{len(out)} berries",
                             detected=[d.berry_id for d in out])
        return out

    # ---- motion ------------------------------------------------------------

    def _drive(self, q_target: np.ndarray, max_s: float = 3.0, level: bool = False) -> None:
        """Hold the position targets until the joints settle or time runs out.

        With `level`, the wrist does not get a fixed target. It follows where
        the shoulder and elbow actually are, every step, so the tray stays flat
        the whole way rather than only at the two ends. Without that, the wrist
        servo arrives in a fraction of a second while the heavier joints take
        seconds, the tray spends the move tipped, and whatever is on it goes
        over the lip — which is what the retract did to 113 of 117 caught
        berries before this existed.
        """
        self.data.ctrl[:] = q_target
        deadline = self.data.time + max_s
        while self.data.time < deadline:
            if level:
                q = self.data.qpos[self.ik.qadr]
                self.data.ctrl[WRIST] = -(q[SHOULDER] + q[ELBOW])
            mujoco.mj_step(self.model, self.data)
            self._scan_contacts()
            self._maybe_frame()
            if (
                np.abs(self.q - q_target).max() < 0.01
                and np.abs(self.data.qvel[self.ik.dofadr]).max() < 0.05
            ):
                return

    def _carry(self, q_target: np.ndarray, settle_s: float = 0.6) -> None:
        """Move with fruit aboard: a smooth trajectory, then a short hold.

        Minimum jerk, because it is the gentlest profile that starts and ends
        at rest, and the duration comes from how far the slowest joint has to
        go. The tray is kept level the whole way.
        """
        q0 = self.q
        dq = q_target - q0
        duration = max(
            CARRY_MIN_S,
            abs(dq[RAIL]) / CARRY_RAIL_M_S,
            float(np.abs(dq[YAW:]).max()) / CARRY_JOINT_RAD_S,
        )
        t0 = self.data.time
        while (tau := (self.data.time - t0) / duration) < 1.0:
            s = tau**3 * (10 - 15 * tau + 6 * tau**2)
            self.data.ctrl[:] = q0 + s * dq
            q = self.data.qpos[self.ik.qadr]
            self.data.ctrl[WRIST] = -(q[SHOULDER] + q[ELBOW])
            mujoco.mj_step(self.model, self.data)
            self._scan_contacts()
            self._maybe_frame()
        self._drive(q_target, max_s=settle_s, level=True)

    def move_to(self, target: np.ndarray, max_s: float = 3.0) -> tuple[bool, float]:
        """Put the cutter at target. Returns (reached, final error)."""
        q_target, residual = self.ik.solve(self.q, target)
        self._drive(q_target, max_s)
        err = float(np.linalg.norm(self.data.site_xpos[self._cutter] - target))
        return err <= REACH_TOL_M, err

    def park(self) -> None:
        self._phase = "retract"
        self._drive(HOME_Q, max_s=3.0)
        self.telemetry.event(self.time, "arm.parked")
        self._phase = "idle"

    # ---- picking -----------------------------------------------------------

    def _displacement(self, berry_id: str) -> float:
        i = self._berry[berry_id]
        return float(np.linalg.norm(self.data.xpos[i] - self._home_pos[berry_id]))

    def _knocked(self, spare: str | None) -> tuple[str, ...]:
        """Berries still on the plant that the arm pressed on. Cut ones are exempt."""
        return tuple(
            sorted(
                bid
                for bid, force in self._force.items()
                if bid != spare and bid not in self._harvested and force > KNOCK_N
            )
        )

    def _berry_at_cutter(self) -> str | None:
        """Whichever stem the blades would close on, or None.

        The robot does not get to name the berry it is cutting. A detection is
        a guess about a position; what actually gets cut is whatever peduncle is
        between the blades. Keeping this geometric is what stops the camera path
        from quietly inheriting the simulator's knowledge of which berry is
        which.
        """
        cutter = self.data.site_xpos[self._cutter]
        best, best_d = None, CUT_REACH_M
        for bid, site in self._cut_site.items():
            if bid in self._harvested:
                continue
            d = float(np.linalg.norm(self.data.site_xpos[site] - cutter))
            if d < best_d:
                best, best_d = bid, d
        return best

    def pick(self, target: DetectedBerry) -> PickResult:
        t0 = self.time
        self._force = {}  # force history is per attempt
        res = PickResult(berry_id=target.berry_id, attempts=1)
        cut_point = target.cut_point
        self.telemetry.event(self.time, "pick.started", target.berry_id,
                             cut_point=[round(float(v), 4) for v in cut_point],
                             est_ripeness=round(target.ripeness, 3))

        # Standoff, then straight in. The baseline always comes in head-on and
        # ignores which way the peduncle runs.
        standoff = cut_point - np.array([0.0, STANDOFF_M, 0.0])
        self._phase = "standoff"
        self.move_to(standoff, max_s=2.5)
        self._phase = "approach"
        res.reached, res.ik_error_m = self.move_to(cut_point, max_s=2.5)
        self.telemetry.event(self.time, "arm.at_cut_point", target.berry_id,
                             reached=res.reached, error_m=round(res.ik_error_m, 4))

        # Whatever fruit the arm leaned on hardest on the way in. Force only
        # means anything while a berry is still attached, so it is read here,
        # before anything is cut.
        attached = {
            bid: f for bid, f in self._force.items() if bid not in self._harvested
        }
        pressed = max(attached, key=attached.get, default=None)
        res.peak_force_n = attached.get(pressed, 0.0) if pressed else 0.0
        victim = self._berry_at_cutter()

        if res.peak_force_n > STEM_TEAR_N:
            res.stem_torn = True
            res.cut_berry_id = pressed
            res.note = (
                f"cutter pressed {res.peak_force_n:.1f} N on {pressed} "
                "while it was still attached"
            )
        elif not res.reached:
            res.note = f"cutter stopped {res.ik_error_m * 1000:.0f} mm from the cut point"
        elif victim is None:
            res.note = "blades closed on nothing: no stem within reach"
        else:
            # Cut: release the peduncle constraint and let the berry fall.
            self.data.eq_active[self._stem[victim]] = 0
            res.cut = True
            res.cut_berry_id = victim
            self._harvested.add(victim)
            self.telemetry.event(self.time, "cutter.cut", victim)
            self._phase = "cut"
            self._settle(0.8)
            res.caught = self._in_tray(victim)
            res.dropped = not res.caught
            if res.caught:
                res.tray_ripeness = self._read_tray()

        # Retract first, then score: the arm can strike fruit on the way out,
        # and that counts.
        if res.caught:
            # Out the way it came in, before anything else moves: a joint-space
            # move from the cut point can swing the tray up into the gutter.
            self._phase = "retract"
            q_out, _ = self.ik.solve(self.q, standoff)
            self._carry(q_out)
            transit = self.data.site_xpos[self._cutter].copy()
            transit[1] = TRANSIT_Y
            q_transit, _ = self.ik.solve(self.q, transit)
            self._carry(q_transit)
            self.place(res, est_radius=target.radius)
        self.park()
        res.knocked = self._knocked(res.cut_berry_id)
        res.duration_s = self.time - t0
        self.telemetry.event(
            self.time,
            "pick.completed" if res.caught else "pick.failed",
            res.note or res.outcome,
            berry_id=target.berry_id,
            cut_berry_id=res.cut_berry_id,
            outcome=res.outcome,
            caught=res.caught,
            knocked=list(res.knocked),
            peak_force_n=round(res.peak_force_n, 2),
            tray_ripeness=(None if res.tray_ripeness is None
                           else round(res.tray_ripeness, 3)),
            duration_s=round(res.duration_s, 2),
        )
        return res

    # ---- placing -----------------------------------------------------------

    def place(self, res: PickResult, est_radius: float) -> None:
        """Carry the caught berry to the next cup and drop it in.

        The tray goes over the cup high, comes straight down to the release
        height, and opens. Where the berry lands and how fast it hits are the
        physics' call; the cell only aims, and aims with what the robot knows:
        the cup it chose and its own estimate of the berry's size.
        """
        berry = res.cut_berry_id
        t0 = self.time
        cell = self._next_cell
        self._next_cell += 1
        res.place_cell = cell
        cx, cy = self._cells[cell]
        self.telemetry.event(self.time, "place.started", berry, cell=cell)

        if not self._on_tray(berry):
            # It rode the carry badly and is already gone.
            res.spilled = True
            res.landed_cell = self._cell_of(berry)
            res.note = "the berry fell from the tray on the way to the punnet"
            self.telemetry.event(self.time, "place.failed", res.note, cell=cell,
                                 landed_cell=res.landed_cell)
            return

        # Put the spot the berry rests on, against the lip, over the cup.
        rest = LIP_FACE_M - est_radius
        floor = scene.PUNNET_FLOOR_Z
        tray_top = np.array([cx, cy - rest, floor + RELEASE_HEIGHT_M])
        # The cutter sits 85 mm above the tray centre and 81 mm above its top.
        drop_at = tray_top + np.array([0.0, 0.0, 0.081])
        q_start = self.q
        q_start[YAW] = 0.0
        q_drop, aim_err = self.place_ik.solve(q_start, drop_at)
        q_hover, _ = self.place_ik.solve(q_drop, drop_at + np.array([0.0, 0.0, HOVER_CLEAR_M]))

        self._carrying, self._impact, self._speed_before = berry, None, 0.0
        self._phase = "place"
        self._carry(q_hover)
        self._carry(q_drop)
        self._open_tray(True)
        self.telemetry.event(self.time, "place.released", berry, cell=cell,
                             aim_error_m=round(aim_err, 4))
        self._settle(0.6)
        # Up and clear before the floor closes, so it does not close on fruit.
        self._carry(q_hover, settle_s=0.2)
        self._open_tray(False)
        self._settle(0.3)
        self._carrying = None

        res.impact_speed_m_s = self._impact
        res.landed_cell = self._cell_of(berry)
        res.spilled = res.landed_cell is None
        if res.spilled:
            res.note = "the berry missed the punnet"
        elif res.landed_cell != cell:
            res.note = f"aimed at cup {cell}, landed in cup {res.landed_cell}"
        elif res.bruised:
            res.note = f"landed at {res.impact_speed_m_s:.2f} m/s: bruised"
        self.telemetry.event(
            self.time,
            "place.completed" if res.packed else "place.failed",
            res.note or "placed",
            cell=cell,
            landed_cell=res.landed_cell,
            impact_speed_m_s=(None if res.impact_speed_m_s is None
                              else round(res.impact_speed_m_s, 3)),
            duration_s=round(self.time - t0, 2),
        )

    def _open_tray(self, open_: bool) -> None:
        """The trapdoor: the tray stops colliding, so whatever is on it falls."""
        for g, (contype, conaffinity) in self._tray_collide.items():
            self.model.geom_contype[g] = 0 if open_ else contype
            self.model.geom_conaffinity[g] = 0 if open_ else conaffinity

    def _cell_of(self, berry_id: str) -> int | None:
        """The cup a berry is resting in, or None if it is not in the punnet.

        A berry on the floor between the two columns is in the punnet but in no
        cup. It is credited to the nearest one, so it reads as misplaced — a
        packer moves it — rather than as lost.
        """
        x, y, z = self.data.xpos[self._berry[berry_id]]
        if not scene.PUNNET_FLOOR_Z - 0.01 < z < scene.PUNNET_FLOOR_Z + scene.PUNNET_WALL_H + 0.03:
            return None  # below the punnet floor, or above it
        half = scene.PUNNET_PITCH / 2
        xs = [cx for cx, _ in self._cells]
        ys = [cy for _, cy in self._cells]
        if not (min(xs) - half < x < max(xs) + half and min(ys) - half < y < max(ys) + half):
            return None
        return min(
            range(len(self._cells)),
            key=lambda i: (x - self._cells[i][0]) ** 2 + (y - self._cells[i][1]) ** 2,
        )

    def _read_tray(self) -> float | None:
        """Look at the fruit in the tray and estimate its ripeness again.

        The survey camera judged this berry from a metre away, possibly through
        a leaf. In the tray it is a hand's width from the wrist camera, lit and
        unobstructed. Harvesters carry an outfeed camera for exactly this, and
        it is the only practical way a machine can tell it picked something
        unripe without waiting for the pack house to say so.
        """
        if self.detector is None:
            return None
        frame = self.capture(scene.WRIST_CAM, *self.camera_size)
        intr = Intrinsics.of(self.model, scene.WRIST_CAM, *self.camera_size)
        pos, mat = camera_pose(self.model, self.data, scene.WRIST_CAM)
        found = self.detector.detect(frame, intr, pos, mat)
        if not found:
            return None
        tray = self.data.geom_xpos[self._tray]
        near = min(found, key=lambda d: float(np.linalg.norm(np.array(d.pos) - tray)))
        if float(np.linalg.norm(np.array(near.pos) - tray)) > 0.12:
            return None  # whatever that was, it is not in the tray
        return float(near.ripeness)

    def _on_tray(self, berry_id: str) -> bool:
        """Resting on the tray, judged in the tray's own frame.

        `_in_tray` is a world-frame test written for the catch, where the tray
        is level and nothing sits below it. Over the punnet a berry already in
        the cup underneath passes that test, so placing asks this instead.
        """
        R = self.data.geom_xmat[self._tray].reshape(3, 3)
        rel = R.T @ (self.data.xpos[self._berry[berry_id]] - self.data.geom_xpos[self._tray])
        return bool(abs(rel[0]) < 0.06 and abs(rel[1]) < 0.065 and 0.0 < rel[2] < 0.05)

    def _in_tray(self, berry_id: str) -> bool:
        berry = self.data.xpos[self._berry[berry_id]]
        tray = self.data.geom_xpos[self._tray]
        return bool(
            float(np.linalg.norm(berry[:2] - tray[:2])) < 0.075
            and berry[2] > tray[2] - 0.02
        )
