"""Rebuild a field harvest attempt in MuJoCo and let the robot try it again.

    uv run python src/harvest/reproduce_scene.py              # all ten attempts
    uv run python src/harvest/reproduce_scene.py --pick p07   # one attempt
    uv run python src/harvest/reproduce_scene.py --snapshots runs/snapshots

For each line of the field log (data/field/harvest_log.jsonl):

  1. find the berries in that attempt's RGB-D image: a YOLO model boxes each
     berry and says if it is ripe; depth gives where each one is
  2. build a MuJoCo scene: those berries, and a 6-axis arm with a cutter
  3. ask robot_controller.py which berry to pick and how, and move the cutter
     along its waypoints
  4. judge the attempt the way the field robot did, and compare with the log

The cutter may touch only stems. A strawberry bruises easily, so the robot's
force sensing stops the attempt the moment the cutter touches any fruit, and
the arm backs out the way it came.

The camera took the image from a fixed place on the robot, so every attempt
shares one camera pose: CAMERA_POSITION, looking along +y.
"""

import argparse
import json
import pathlib

import mujoco
import numpy as np
from PIL import Image as pil_image
import ultralytics

import robot_controller

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIELD = ROOT / "data" / "field"

CAMERA_POSITION = np.array([0.0, 0.18, 0.45])  # world, metres
MAX_BERRY_DEPTH = 0.41  # nearer than this is the plant in front of the robot; farther is gutter and leaves
DETECTOR = ROOT / "models" / "strawberry_yolo.pt"  # made by src/perception/strawberry_perception_trainer.py
MIN_CONFIDENCE = 0.5
_detector = None  # loaded on first use
CAMERA_FOVY = 56.1  # degrees: 640 pixels high at a focal length of 600 pixels

TOOL_SPEED = 0.10  # m/s
CUT_TIME = 1.0  # seconds the cutter takes to close
FORCE_LIMIT = 0.05  # N on any fruit: a touch. The cutter may touch only stems, so the robot stops
RETREAT = 0.10  # m the cutter backs out along its approach after it touches a fruit
REACH_TOLERANCE = 0.005  # m between the cutter tip and the cut point
FILM_FPS = 30


# ---- 1. berries from the image ----------------------------------------------------


def detect(rgb: np.ndarray) -> list[tuple[np.ndarray, bool, float]]:
    """YOLO boxes (x0, y0, x1, y1 in pixels) in an RGB image, each with whether the berry is ripe,
    and how sure the model is."""
    global _detector
    if _detector is None:
        _detector = ultralytics.YOLO(str(DETECTOR))
    bgr = np.ascontiguousarray(rgb[..., ::-1])  # ultralytics takes arrays in OpenCV's BGR order
    boxes = _detector(bgr, conf=MIN_CONFIDENCE, verbose=False)[0].boxes
    names = _detector.names
    return [(box, names[int(cls)] == "ripe", float(conf))
            for box, cls, conf in zip(boxes.xyxy.cpu().numpy(), boxes.cls, boxes.conf)]


def find_berries(rgb: np.ndarray, depth_mm: np.ndarray, camera: dict) -> list[robot_controller.Berry]:
    """Berries in an RGB-D image, in the world frame: YOLO says where and which, depth says how far."""
    berries = []
    for (x0, y0, x1, y1), ripe, _ in detect(rgb):
        # Depth in the middle of the box: the berry itself, not the leaves around it.
        dx, dy = (x1 - x0) / 4, (y1 - y0) / 4
        patch = depth_mm[int(y0 + dy):int(y1 - dy) + 1, int(x0 + dx):int(x1 - dx) + 1]
        patch = patch[(patch > 0) & (patch < MAX_BERRY_DEPTH * 1000)]
        if patch.size == 0:
            continue
        surface = np.median(patch) / 1000
        radius = (x1 - x0) / 2 * surface / camera["fx"]
        z = surface + radius  # the centre is one radius behind the surface we see
        x = ((x0 + x1) / 2 - camera["cx"]) / camera["fx"] * z
        y = ((y0 + y1) / 2 - camera["cy"]) / camera["fy"] * z
        # Camera frame (x right, y down, z forward) to world (x right, y forward, z up).
        center = CAMERA_POSITION + np.array([x, z, -y])
        berries.append(robot_controller.Berry(center, radius, ripe))
    return berries


# ---- 2. the MuJoCo scene ----------------------------------------------------------

ARM = """
<body name="base" pos="0 0 0" childclass="arm">
  <geom type="cylinder" size="0.06 0.045" pos="0 0 0.045" rgba="0.3 0.3 0.32 1"/>
  <body name="shoulder" pos="0 0 0.09">
    <joint name="j1" axis="0 0 1"/>
    <geom type="cylinder" size="0.045 0.04" rgba="0.85 0.85 0.85 1"/>
    <body name="upper_arm">
      <joint name="j2" axis="1 0 0"/>
      <geom type="capsule" fromto="0 0 0 0 0 0.35" size="0.035" rgba="0.85 0.85 0.85 1"/>
      <body name="forearm" pos="0 0 0.35">
        <joint name="j3" axis="1 0 0"/>
        <geom type="capsule" fromto="0 0 0 0 0 0.25" size="0.03" rgba="0.85 0.85 0.85 1"/>
        <body name="wrist1" pos="0 0 0.25">
          <joint name="j4" axis="1 0 0"/>
          <geom type="capsule" fromto="0 0 0 0 0 0.06" size="0.025" rgba="0.3 0.3 0.32 1"/>
          <body name="wrist2" pos="0 0 0.06">
            <joint name="j5" axis="0 1 0"/>
            <geom type="capsule" fromto="0 0 0 0 0 0.05" size="0.025" rgba="0.3 0.3 0.32 1"/>
            <body name="cutter" pos="0 0 0.05">
              <joint name="j6" axis="0 0 1"/>
              <geom type="box" size="0.012 0.008 0.05" pos="0 0 0.05" rgba="0.6 0.62 0.65 1"/>
              <geom type="box" size="0.010 0.002 0.012" pos="0 0 0.112" rgba="0.75 0.77 0.8 1"/>
              <site name="tip" pos="0 0 0.124" size="0.003"/>
            </body>
          </body>
        </body>
      </body>
    </body>
  </body>
</body>
"""

HOME_TIP = np.array([0.0, 0.30, 0.42])  # where the cutter waits, well in front of the plant
HOME_GUESS = np.array([0.0, 0.2, -1.8, 0.0, 0.0, 0.0])  # elbow up, cutter forward
ARM_JOINTS = 6  # first in qpos; the stems' joints follow

STEM_LENGTH = 0.2  # m from the top of the fruit straight up to where the stem hangs from
STEM_POINTS = 9  # points along the rod; one sits at the cut point
STEM_RADIUS = 0.0015  # m
STEM_YOUNG = 2e7  # Pa: Young's modulus of a green strawberry stem, roughly
STEM_MASS = 0.002  # kg, the whole stem


def _vec(v) -> str:
    return " ".join(f"{c:.5f}" for c in v)


def stem_points(berry: robot_controller.Berry) -> np.ndarray:
    """The stem's points, from where it hangs down to the top of the fruit.

    The stem hangs straight down, so the berry hangs where the camera saw it
    without bending the stem. The point before the last is the cut point.
    """
    cut = robot_controller.CUT_ABOVE_TOP
    heights = np.concatenate([np.linspace(STEM_LENGTH, cut, STEM_POINTS - 1), [0.0]])
    return np.array([berry.top + [0.0, 0.0, h] for h in heights])


def cut_body(i: int) -> str:
    """The stem body at berry i's cut point."""
    return f"stem{i}_{STEM_POINTS - 2}"


def _hanging_berry(i: int, berry: robot_controller.Berry) -> str:
    """A berry on an elastic rod: MuJoCo's 1D flexcomp, with bending and twist.

    The rod is pinned at the top, cannot stretch, and bends with STEM_YOUNG,
    so a pushed berry swings away and the stem gives way instead of standing
    like a wall. The fruit is its own free body, joined to the rod's lower end.
    """
    points = stem_points(berry)
    elements = " ".join(f"{k} {k + 1}" for k in range(STEM_POINTS - 1))
    color = "0.75 0.05 0.05 1" if berry.ripe else "0.75 0.8 0.5 1"
    return (
        f'<flexcomp name="stem{i}" type="direct" dim="1" point="{_vec(points.ravel())}" element="{elements}" '
        f'radius="{STEM_RADIUS}" mass="{STEM_MASS}" inertiabox="0.001" rgba="0.2 0.45 0.1 1">'
        f'<pin id="0 1"/>'  # clamped where it hangs from
        f'<edge equality="true" solref="0.002 1" solimp="0.99 0.999 0.001"/>'  # it does not stretch
        f'<contact contype="0" conaffinity="0"/>'  # the cutter passes through stems
        f'<elasticity young="{STEM_YOUNG}" poisson="0.3" damping="0.001"/>'
        f'</flexcomp>'
        f'<body name="fruit{i}" pos="{_vec(berry.top)}"><freejoint/>'
        f'<geom name="berry{i}" type="ellipsoid" pos="{_vec(berry.center - berry.top)}" '
        f'size="{berry.radius} {berry.radius} {1.4 * berry.radius}" rgba="{color}"/>'  # fruit touch fruit, too
        f'</body>'
    )


def _stem_joins(berries: list[robot_controller.Berry]) -> str:
    """Each fruit hangs from the lower end of its stem."""
    return "".join(f'<connect body1="fruit{i}" body2="stem{i}_{STEM_POINTS - 1}" anchor="0 0 0" solref="0.002 1" solimp="0.99 0.999 0.001"/>'
                   for i in range(len(berries)))


def build_scene(berries: list[robot_controller.Berry]) -> mujoco.MjModel:
    """The arm, the berries hanging on their stems, and a gutter behind them."""
    parts = [_hanging_berry(i, berry) for i, berry in enumerate(berries)]
    gutter_y = max(b.center[1] for b in berries) + 0.12
    xml = f"""
<mujoco>
  <!-- discrete: MuJoCo integrates rod elasticity implicitly only with this integrator -->
  <option timestep="0.001" integrator="discrete" solver="Newton"/>
  <visual><global offwidth="640" offheight="640"/></visual>
  <default>
    <default class="arm">
      <joint armature="0.1" damping="5"/>  <!-- motor and gearbox inertia keep the light links stable -->
      <geom contype="1" conaffinity="0"/>  <!-- the arm touches berries, not itself -->
    </default>
  </default>
  <worldbody>
    <light pos="0 -0.5 1.5" dir="0 0.3 -1"/>
    <geom type="plane" size="1 1 0.01" rgba="0.8 0.8 0.78 1" contype="0" conaffinity="0"/>
    <!-- The robot's camera, where it took the field image: looking along +y, z up. -->
    <camera name="robot" pos="{CAMERA_POSITION[0]} {CAMERA_POSITION[1]} {CAMERA_POSITION[2]}"
            xyaxes="1 0 0 0 0 1" fovy="{CAMERA_FOVY}"/>
    <geom type="box" pos="0 {gutter_y} 0.72" size="0.6 0.05 0.04" rgba="0.9 0.9 0.88 1"
          contype="0" conaffinity="0"/>
    {ARM.replace("<body ", '<body gravcomp="1" ')}  <!-- the motors hold the arm up against gravity -->
    {''.join(parts)}  <!-- after the arm, so the arm's joints come first in qpos -->
  </worldbody>
  <equality>{_stem_joins(berries)}</equality>
  <actuator>
    {''.join(f'<position joint="j{k}" kp="400" kv="20"/>' for k in range(1, 7))}
  </actuator>
</mujoco>
"""
    return mujoco.MjModel.from_xml_string(xml)


# ---- 3. moving the cutter ---------------------------------------------------------


def solve_ik(model, goal: np.ndarray, direction: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Joint angles that put the tip at `goal` with the cutter pointing along `direction`."""
    site = model.site("tip").id
    jacp, jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))
    data = mujoco.MjData(model)  # a scratch copy, so the simulation keeps its state
    data.qpos[:ARM_JOINTS] = q
    for _ in range(100):
        mujoco.mj_kinematics(model, data)
        mujoco.mj_comPos(model, data)
        position_error = goal - data.site_xpos[site]
        pointing = data.site_xmat[site].reshape(3, 3)[:, 2]
        angle_error = np.cross(pointing, direction)
        error = np.concatenate([position_error, 0.3 * angle_error])
        if np.linalg.norm(error) < 1e-5:
            break
        mujoco.mj_jacSite(model, data, jacp, jacr, site)
        jac = np.vstack([jacp, 0.3 * jacr])[:, :ARM_JOINTS]
        data.qpos[:ARM_JOINTS] += jac.T @ np.linalg.solve(jac @ jac.T + 1e-4 * np.eye(6), error)
    return data.qpos[:ARM_JOINTS].copy()


class Run:
    """One attempt in the simulator: moves the arm and records what it touched."""

    def __init__(self, model, target: int):
        self.model, self.data = model, mujoco.MjData(model)
        self.target = target  # index of the berry being picked
        forward = np.array([0.0, 1.0, 0.0])
        self.data.qpos[:ARM_JOINTS] = self.data.ctrl[:] = solve_ik(model, HOME_TIP, forward, HOME_GUESS)
        mujoco.mj_forward(model, self.data)
        self.tip = self.data.site("tip").xpos.copy()
        self.direction = forward
        self.peak_force = 0.0  # of the arm on any fruit, the target's included
        self.renderer, self.frames = None, []  # set renderer to film the attempt
        self.cut = False

    def _step(self, steps: int) -> None:
        force = np.zeros(6)
        for _ in range(steps):
            mujoco.mj_step(self.model, self.data)
            if self.renderer and self.data.time >= len(self.frames) / FILM_FPS:
                self.renderer.update_scene(self.data, side_view())
                self.frames.append(self.renderer.render())
            for i in range(self.data.ncon):
                contact = self.data.contact[i]
                fruit = [self.model.geom(g).name.startswith("berry") for g in (contact.geom1, contact.geom2)]
                if sum(fruit) == 1:  # the arm on a fruit; fruit on fruit is not the robot's touch
                    mujoco.mj_contactForce(self.model, self.data, i, force)
                    self.peak_force = max(self.peak_force, force[0])

    @property
    def touched(self) -> bool:
        return self.peak_force > FORCE_LIMIT

    def move(self, waypoint: robot_controller.Waypoint, stop_on_touch: bool = True) -> None:
        """Move the tip in a straight line, at TOOL_SPEED, to the waypoint.

        The robot stops where it is the moment the cutter touches a fruit.
        """
        distance = np.linalg.norm(waypoint.position - self.tip)
        n = max(1, int(distance / 0.002))
        q = self.data.ctrl.copy()
        for k in range(1, n + 1):
            t = k / n
            goal = self.tip + t * (waypoint.position - self.tip)
            direction = (1 - t) * self.direction + t * waypoint.direction
            q = solve_ik(self.model, goal, direction / np.linalg.norm(direction), q)
            self.data.ctrl[:] = q
            self._step(int(0.002 / TOOL_SPEED / self.model.opt.timestep))
            if stop_on_touch and self.touched:
                self.tip, self.direction = goal, direction / np.linalg.norm(direction)
                return
        self.tip, self.direction = waypoint.position, waypoint.direction
        if waypoint.cut:
            self._step(int(CUT_TIME / self.model.opt.timestep))
            # Judged at the target's stem as it is now: a berry pushed aside takes its cut point with it.
            reached = np.linalg.norm(self.data.site("tip").xpos - self.data.body(cut_body(self.target)).xpos)
            self.cut = reached < REACH_TOLERANCE


# ---- 4. one attempt, start to finish ----------------------------------------------


def reproduce(line: dict, camera: dict, snapshot_dir: pathlib.Path | None = None, film: bool = False) -> dict:
    """Rebuild one logged attempt and run the robot controller on it.

    With `film`, the result also holds the attempt's video frames, and the
    berries the camera found.
    """
    pick = line["pick"]
    rgb = np.asarray(pil_image.open(FIELD / "images" / f"{pick}_rgb.png").convert("RGB"))
    depth = np.asarray(pil_image.open(FIELD / "images" / f"{pick}_depth.png"))
    berries = find_berries(rgb, depth, camera)
    target = robot_controller.choose_target(berries, CAMERA_POSITION)
    if target is None:
        return {"pick": pick, "berries": len(berries), "outcome": "no_target", "peak_force_n": 0.0, "cycle_s": 0.0}

    model = build_scene(berries)
    run = Run(model, next(i for i, berry in enumerate(berries) if berry is target))
    if film:
        run.renderer = mujoco.Renderer(model, 480, 640)
    for waypoint in robot_controller.plan(target, berries):
        run.move(waypoint)
        if run.touched:  # it stopped at the touch; back out the way it came, and give up this berry
            run.move(robot_controller.Waypoint(run.tip - RETREAT * run.direction, run.direction), stop_on_touch=False)
            break
    if snapshot_dir:
        save_snapshot(model, run.data, snapshot_dir / f"{pick}.png")

    if run.touched:
        outcome = "fruit_contact"  # the cutter touched a fruit, which it must not
    elif not run.cut:
        outcome = "missed"
    else:
        outcome = "picked"
    result = {"pick": pick, "berries": len(berries), "outcome": outcome,
              "peak_force_n": round(run.peak_force, 1), "cycle_s": round(run.data.time, 1)}
    if film:
        run.renderer.close()
        result.update(frames=run.frames, found=berries, target=target, model=model)
    return result


def side_view() -> mujoco.MjvCamera:
    """Beside the arm and a little above it, for pictures and videos."""
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0.0, 0.35, 0.4]
    camera.distance, camera.azimuth, camera.elevation = 1.2, 150, -20
    return camera


def save_snapshot(model, data, path: pathlib.Path) -> None:
    """A picture of the scene, from the side and a little above."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with mujoco.Renderer(model, 480, 640) as renderer:
        renderer.update_scene(data, side_view())
        pil_image.fromarray(renderer.render()).save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pick", help="only this attempt, e.g. p07")
    parser.add_argument("--snapshots", type=pathlib.Path, help="save a picture of each attempt here")
    args = parser.parse_args()

    camera = json.loads((ROOT / "data" / "camera.json").read_text())
    lines = [json.loads(s) for s in (FIELD / "harvest_log.jsonl").read_text().splitlines()]
    if args.pick:
        lines = [line for line in lines if line["pick"] == args.pick]

    matched = picked = 0
    print(f"{'pick':5} {'field':10} {'simulation':10} {'force N':>8} {'cycle s':>8}  berries")
    for line in lines:
        result = reproduce(line, camera, args.snapshots)
        same = result["outcome"] == line["outcome"]
        matched += same
        picked += result["outcome"] == "picked"
        print(f"{line['pick']:5} {line['outcome']:10} {result['outcome']:10} "
              f"{result['peak_force_n']:8.1f} {result['cycle_s']:8.1f}  {result['berries']}"
              f"{'' if same else '   <- differs from the field'}")
    print(f"{matched} of {len(lines)} attempts end as they did in the field")
    print(f"{picked} of {len(lines)} attempts picked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
