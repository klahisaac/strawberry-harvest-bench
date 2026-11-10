"""MJCF generation: a Scenario becomes a MuJoCo model.

The parallel with lab-robot is deliberate. There, `protocol.py` turns a plate
plan into an Opentrons protocol that the official simulator runs. Here,
`scene.py` turns a scenario into MJCF that MuJoCo steps. In both cases the
generated artifact is saved, so a run can be inspected and replayed.

Each berry is a free body held by a weld constraint standing in for its
peduncle. Cutting the stem means deactivating that constraint, after which the
berry is subject to gravity and either lands on the tray or is dropped.
"""

import math

import numpy as np

from .scenario import BERRY_MASS, GUTTER_FACE_Y, GUTTER_TOP_Z, GUTTER_X, Scenario

# Arm geometry (metres).
RAIL_RANGE = (0.0, 1.20)
SHOULDER_Z = 0.95
UPPER_LEN = 0.30
FORE_LEN = 0.28

ARM_JOINTS = ("rail", "yaw", "shoulder", "elbow", "wrist")
# Every arm geom sits in this group, so a render can leave the arm out.
ARM_GEOM_GROUP = 3
CUTTER_SITE = "cutter"
TRAY_GEOM = "tray"
WRIST_CAM = "wrist_cam"
SURVEY_CAM = "survey_cam"

# Above this occlusion a berry gets a physical leaf in front of it.
LEAF_OCCLUSION_MIN = 0.25

# The punnet: a packing tray of cups at the home end of the rail, where the arm
# already returns after every pick. Real harvesters pack in the field — a berry
# handled twice is a berry bruised twice — so the bench has to as well.
#
# It sits below and to the side of the survey camera's view. Perception must not
# change because a tray was added to the cell, and the fingerprint test holds
# the survey frame to that.
PUNNET_COLS = 2
PUNNET_PITCH = 0.050  # cup size, and row to row (metres)
# Column to column. Wider than the catch tray, so placing a berry in one
# column never brings the tray down over fruit already sitting in the other.
# With the columns side by side, the second cup in every row missed far more
# often.
PUNNET_COL_PITCH = 0.110
PUNNET_X0 = 0.000  # first column, on the rail axis at rail = 0
PUNNET_Y0 = 0.100  # first row, nearest the rail
PUNNET_FLOOR_Z = 0.330  # top of the cup floor
PUNNET_WALL_H = 0.018  # cup depth: a shallow insert, like a real clamshell
PUNNET_GEOM_PREFIX = "punnet"


def punnet_cells(scenario: Scenario) -> list[tuple[float, float]]:
    """Cup centres (x, y), in packing order.

    Enough cups for every berry in the scenario, so the robot never has to deal
    with a full punnet. Shared by the MJCF builder and the cell.

    Packing starts at the far row and works toward the rail. Over a cup the
    tray hangs out toward the rail by most of its length, so filling the near
    rows first would have it come down on fruit already packed.
    """
    rows = max(3, math.ceil(len(scenario.berries) / PUNNET_COLS))
    return [
        (PUNNET_X0 + c * PUNNET_COL_PITCH, PUNNET_Y0 + r * PUNNET_PITCH)
        for r in reversed(range(rows))
        for c in range(PUNNET_COLS)
    ]


def _punnet(scenario: Scenario) -> str:
    """The cup tray: a floor and a grid of low walls, all colliding.

    Collision matters here, unlike the decoration on the fruit. Whether a berry
    lands in its cup, the next one, or over the side, and how hard it hits, is
    exactly what the place step is meant to measure.
    """
    cells = punnet_cells(scenario)
    xs = sorted({x for x, _ in cells})
    ys = sorted({y for _, y in cells})
    half = PUNNET_PITCH / 2
    x0, x1 = xs[0] - half, xs[-1] + half
    y0, y1 = ys[0] - half, ys[-1] + half
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    wall_z = PUNNET_FLOOR_Z + PUNNET_WALL_H / 2
    t = 0.0015  # wall half-thickness
    p = PUNNET_GEOM_PREFIX
    parts = [
        f'    <body name="punnet">\n'
        f'      <geom name="{p}_floor" type="box" size="{hx:.4f} {hy:.4f} 0.003"'
        f' pos="{cx:.4f} {cy:.4f} {PUNNET_FLOOR_Z - 0.003:.4f}" material="punnet"/>\n'
    ]
    # Each column is its own strip of cups; the floor runs under the gap.
    for i, x in enumerate(sorted({x + d for x in xs for d in (-half, half)})):
        parts.append(
            f'      <geom name="{p}_wx{i}" type="box" size="{t} {hy:.4f} {PUNNET_WALL_H / 2:.4f}"'
            f' pos="{x:.4f} {cy:.4f} {wall_z:.4f}" material="punnet"/>\n'
        )
    for j, y in enumerate([y0] + [y + half for y in ys]):
        parts.append(
            f'      <geom name="{p}_wy{j}" type="box" size="{hx:.4f} {t} {PUNNET_WALL_H / 2:.4f}"'
            f' pos="{cx:.4f} {y:.4f} {wall_z:.4f}" material="punnet"/>\n'
        )
    parts.append("    </body>\n")
    return "".join(parts)


# Offscreen buffer for the wrist camera. MuJoCo refuses a render larger than
# this, and the default is small, so it is declared up front.
OFFSCREEN = (1280, 960)

_HEADER = f"""<mujoco model="harvest-cell">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <compiler angle="radian" autolimits="true"/>
  <visual>
    <global offwidth="{OFFSCREEN[0]}" offheight="{OFFSCREEN[1]}"/>
    <quality shadowsize="4096"/>
    <headlight ambient="0.55 0.55 0.55" diffuse="0.45 0.45 0.45" specular="0.2 0.2 0.2"/>
  </visual>
  <default>
    <joint damping="2.0" armature="0.05"/>
    <geom friction="1.2 0.02 0.001"/>
    <position kp="400" dampratio="1.2" forcerange="-200 200"/>
  </default>
"""


def leaves(scenario: Scenario) -> list[dict]:
    """Where the occluding leaves sit, as plain boxes.

    Placement is shared with nothing else on purpose: the leaves the physics
    collides with are the leaves the camera sees.

    Placement comes from each berry's own random stream, so how badly a leaf is
    in the way varies. One squarely over the cut point blocks a head-on approach
    outright; one offset to the side or riding high leaves a gap. That turns
    occlusion into a gradient instead of a cliff, which is what makes the
    success-by-occlusion metric worth reading.
    """
    out = []
    for b in scenario.berries:
        if b.occlusion <= LEAF_OCCLUSION_MIN:
            continue
        bx, by, bz = b.pos
        # A stream of its own, so leaf placement does not correlate with the
        # sensor noise drawn from the same berry elsewhere.
        rng = b.rng(scenario.seed + 7777)
        out.append(
            {
                "berry_id": b.berry_id,
                "pos": (
                    bx + float(rng.uniform(-0.055, 0.055)),
                    by - 0.045,
                    bz + float(rng.uniform(0.0, 0.055)),
                ),
                "half": (0.020 + 0.030 * b.occlusion, 0.004, 0.028),
            }
        )
    return out


def _ripeness_rgb(ripeness: float) -> tuple[str, str]:
    """The two ends of a berry's gradient, pale green through deep red.

    Colour has to carry ripeness, because that is what a camera-based detector
    has to read it from. A material `rgba` will not do the job: once a texture
    is attached it wins, so every berry gets a texture of its own.
    """
    pale = (0.72, 0.78, 0.42), (0.45, 0.58, 0.26)
    ripe = (0.86, 0.10, 0.13), (0.50, 0.03, 0.07)
    mix = lambda a, b: " ".join(  # noqa: E731
        f"{a[i] * (1 - ripeness) + b[i] * ripeness:.3f}" for i in range(3)
    )
    return mix(pale[0], ripe[0]), mix(pale[1], ripe[1])


def _assets(scenario: Scenario) -> str:
    """Textures and materials. One pair per berry, keyed to its ripeness."""
    parts = ["  <asset>\n"]
    for b in scenario.berries:
        lo, hi = _ripeness_rgb(b.ripeness)
        parts.append(
            f'    <texture name="{b.berry_id}_tex" type="cube" builtin="gradient"'
            f' width="128" height="128" rgb1="{lo}" rgb2="{hi}"'
            # The speckle marks stand in for achenes. They are also the texture
            # noise a colour-threshold detector has to cope with.
            f' mark="random" markrgb="0.97 0.90 0.52" random="0.015"/>\n'
            f'    <material name="{b.berry_id}_mat" texture="{b.berry_id}_tex"'
            f' specular="0.85" shininess="0.7" reflectance="0.05"/>\n'
        )
    parts.append(
        '    <texture name="leaftex" type="cube" builtin="flat" width="64" height="64"'
        ' rgb1="0.14 0.34 0.15" rgb2="0.14 0.34 0.15"'
        ' mark="random" markrgb="0.21 0.46 0.21" random="0.03"/>\n'
        '    <material name="leaf" texture="leaftex" specular="0.3" shininess="0.35"/>\n'
        '    <texture name="canopytex" type="cube" builtin="flat" width="128" height="128"'
        ' rgb1="0.10 0.26 0.12" rgb2="0.10 0.26 0.12"'
        ' mark="random" markrgb="0.19 0.44 0.20" random="0.08"/>\n'
        '    <material name="canopy" texture="canopytex" specular="0.15" shininess="0.2"/>\n'
        '    <material name="calyx" rgba="0.24 0.50 0.22 1" specular="0.35" shininess="0.3"/>\n'
        '    <material name="steel" rgba="0.55 0.57 0.60 1" specular="0.6" shininess="0.5"/>\n'
        '    <material name="gutter" rgba="0.35 0.32 0.30 1"/>\n'
        '    <material name="punnet" rgba="0.86 0.88 0.90 1" specular="0.5" shininess="0.6"/>\n'
        "  </asset>\n"
    )
    return "".join(parts)


def _berry_body(b) -> str:
    """One berry: a colliding ellipsoid plus decoration.

    Only the main ellipsoid collides. The tip, the sepals and the stem are
    `contype=0 conaffinity=0`, so the physics — and every force threshold
    calibrated against it — depends on one simple shape, while the camera sees
    something that reads as fruit.
    """
    bx, by, bz = b.pos
    r, h = b.radius, b.half_height
    sepals = []
    for k in range(5):
        a = 2 * math.pi * k / 5
        sepals.append(
            f'      <geom type="ellipsoid" size="{r * 0.55:.4f} {r * 0.22:.4f} 0.0018"'
            f' pos="{r * 0.62 * math.cos(a):.4f} {r * 0.62 * math.sin(a):.4f} {h * 0.86:.4f}"'
            f' euler="0 -0.45 {a:.3f}" material="calyx" contype="0" conaffinity="0"/>\n'
        )
    return (
        f'    <body name="{b.berry_id}_anchor" pos="{bx:.4f} {by:.4f} {bz:.4f}">\n'
        f'      <geom type="sphere" size="0.002" mass="0" rgba="0 0 0 0"'
        f' contype="0" conaffinity="0"/>\n'
        f"    </body>\n"
        f'    <body name="{b.berry_id}" pos="{bx:.4f} {by:.4f} {bz:.4f}">\n'
        f"      <freejoint/>\n"
        f'      <geom name="{b.berry_id}_geom" type="ellipsoid"'
        f' size="{r:.4f} {r:.4f} {h:.4f}" mass="{BERRY_MASS}"'
        f' material="{b.berry_id}_mat"/>\n'
        f'      <geom type="ellipsoid" size="{r * 0.62:.4f} {r * 0.62:.4f} {h * 0.42:.4f}"'
        f' pos="0 0 {-h * 0.78:.4f}" material="{b.berry_id}_mat"'
        f' contype="0" conaffinity="0"/>\n'
        f"{''.join(sepals)}"
        f'      <geom type="capsule" fromto="0 0 {h * 0.9:.4f} 0.002 0.004 {h + 0.022:.4f}"'
        f' size="0.0022" material="calyx" contype="0" conaffinity="0"/>\n'
        f'      <site name="{b.berry_id}_cut" pos="0 0 {h + 0.012:.4f}" size="0.004"'
        f' rgba="1 1 0 0.6"/>\n'
        f"    </body>\n"
    )


def build(scenario: Scenario, leaf_boxes: list[dict] | None = None) -> str:
    """The full MJCF for this scenario.

    `leaf_boxes` replaces the generated leaves. A world rebuilt from a field
    log has no generator behind it, only the leaves it could see in the
    picture, so those are what it passes here.
    """
    x0, x1 = GUTTER_X
    cx = (x0 + x1) / 2
    half = (x1 - x0) / 2

    parts = [_HEADER, _assets(scenario), "  <worldbody>\n"]
    # Grow lights above the row, plus a fill from the aisle so the fruit is not
    # lit only from one side. Under-lit fruit is a different, easier perception
    # problem than the real one.
    #
    # Brightness and tint vary per scenario. Without that, hue predicts ripeness
    # almost exactly and reading ripeness off colour stops being a problem worth
    # solving. Lighting is also the thing a fixed threshold is least robust to,
    # which is the point.
    lrng = np.random.default_rng(scenario.seed + 4242)
    # Hue is invariant to brightness, so `level` alone changes nothing a colour
    # threshold cares about. The tint is what moves it, and grow lights really
    # do differ this much in colour temperature.
    level = float(lrng.uniform(0.62, 1.00))
    warm = float(lrng.uniform(-0.18, 0.18))
    grow = f"{level * (1 + warm):.3f} {level:.3f} {level * (1 - warm) * 0.94:.3f}"
    fill = f"{level * 0.5 * (1 + warm):.3f} {level * 0.5:.3f} {level * 0.5 * (1 - warm):.3f}"
    parts.append(
        f'    <light pos="{cx - 0.35:.3f} 0.30 1.55" dir="0.1 -0.1 -1"'
        f' diffuse="{grow}" specular="0.45 0.45 0.45"/>\n'
        f'    <light pos="{cx + 0.35:.3f} 0.30 1.55" dir="-0.1 -0.1 -1"'
        f' diffuse="{grow}" specular="0.45 0.45 0.45"/>\n'
        f'    <light pos="{cx:.3f} -0.70 1.10" dir="0 0.5 -0.6"'
        f' diffuse="{fill}" specular="0.15 0.15 0.15" castshadow="false"/>\n'
    )
    parts.append('    <geom name="floor" type="plane" size="3 3 0.1" rgba="0.18 0.18 0.2 1"/>\n')

    # A fixed camera facing the gutter, wide enough to take in the whole row.
    # Perception plans from this view; the wrist camera is for the close-up.
    #
    # A real machine would carry this on the carriage and scan. One fixed view
    # is a simplification, and it is the reason occlusion here is a property of
    # one viewpoint rather than of the approach the arm ends up taking.
    parts.append(
        f'    <camera name="{SURVEY_CAM}" pos="{cx:.3f} -0.45 0.820"'
        f' xyaxes="1 0 0 0 0.10 1" fovy="55"/>\n'
    )

    # The gutter the plants sit in. Its front face is what the arm reaches past.
    parts.append(
        f'    <body name="gutter" pos="{cx:.3f} {GUTTER_FACE_Y + 0.10:.3f} {GUTTER_TOP_Z:.3f}">\n'
        f'      <geom name="gutter_box" type="box" size="{half:.3f} 0.10 0.04" material="gutter"/>\n'
        f"    </body>\n"
    )

    # Berries: free bodies, each held by a weld to a static anchor standing in
    # for the peduncle. The anchor sits exactly where the berry starts, so the
    # welded relative pose is the identity and the berry stays put until cut.
    for b in scenario.berries:
        parts.append(_berry_body(b))
    # Canopy behind the fruit. Without it the survey camera sees red fruit on
    # black, and picking the fruit out is trivial for any method — which would
    # make comparing one detector against another meaningless. A cluttered
    # green background is what makes the problem the real one: distractors,
    # low contrast at the edges, and leaves that are not in front of anything.
    parts.append(
        f'    <body name="canopy" pos="{cx:.3f} 0.515 0.760">\n'
        f'      <geom name="canopy_geom" type="box" size="{half + 0.10:.3f} 0.004 0.130"'
        f' material="canopy" contype="0" conaffinity="0"/>\n'
        f"    </body>\n"
    )
    clutter = np.random.default_rng(scenario.seed + 991)
    for i in range(14):
        cxx = clutter.uniform(x0 - 0.05, x1 + 0.05)
        czz = clutter.uniform(0.66, 0.88)
        cyy = clutter.uniform(0.46, 0.51)
        sx = clutter.uniform(0.022, 0.055)
        sz = clutter.uniform(0.016, 0.034)
        parts.append(
            f'    <body name="clutter{i}" pos="{cxx:.4f} {cyy:.4f} {czz:.4f}">\n'
            f'      <geom type="box" size="{sx:.4f} 0.003 {sz:.4f}" material="leaf"'
            f' euler="{clutter.uniform(-0.4, 0.4):.3f} {clutter.uniform(-0.6, 0.6):.3f} 0"'
            f' contype="0" conaffinity="0"/>\n'
            f"    </body>\n"
        )

    # Leaves in front of occluded berries, so occlusion is physical and not just
    # a number: the arm can actually collide with one. See `leaves()`.
    for leaf in leaves(scenario) if leaf_boxes is None else leaf_boxes:
        lx, ly, lz = leaf["pos"]
        hx, hy, hz = leaf["half"]
        parts.append(
            f'    <body name="{leaf["berry_id"]}_leaf" pos="{lx:.4f} {ly:.4f} {lz:.4f}">\n'
            f'      <geom name="{leaf["berry_id"]}_leafgeom" type="box"'
            f' size="{hx:.4f} {hy:.4f} {hz:.4f}" material="leaf"/>\n'
            f"    </body>\n"
        )

    parts.append(_punnet(scenario))

    # The arm: a rail carriage, a yaw joint, then a planar two-link arm and a
    # wrist. Five degrees of freedom is enough to reach a cut point and choose
    # an approach angle, and it keeps the inverse kinematics well conditioned.
    parts.append(
        f'    <body name="carriage" pos="0 0 {SHOULDER_Z:.3f}">\n'
        f'      <joint name="rail" type="slide" axis="1 0 0" range="{RAIL_RANGE[0]} {RAIL_RANGE[1]}"/>\n'
        f'      <geom group="3" type="box" size="0.05 0.05 0.03" material="steel"/>\n'
        f'      <body name="yaw_link">\n'
        f'        <joint name="yaw" type="hinge" axis="0 0 1" range="-0.9 0.9"/>\n'
        f'        <geom group="3" type="cylinder" size="0.030 0.020" material="steel"/>\n'
        f'        <body name="upper">\n'
        f'          <joint name="shoulder" type="hinge" axis="1 0 0" range="-2.4 2.4"/>\n'
        f'          <geom group="3" type="capsule" fromto="0 0 0 0 {UPPER_LEN:.3f} 0" size="0.022" material="steel"/>\n'
        f'          <body name="fore" pos="0 {UPPER_LEN:.3f} 0">\n'
        f'            <joint name="elbow" type="hinge" axis="1 0 0" range="-2.6 2.6"/>\n'
        f'            <geom group="3" type="capsule" fromto="0 0 0 0 {FORE_LEN:.3f} 0" size="0.018" material="steel"/>\n'
        f'            <body name="wrist" pos="0 {FORE_LEN:.3f} 0">\n'
        # Wide enough to keep the tray level with the arm reaching down to the
        # punnet. At +-1.6 it could not be held flat over the cups.
        f'              <joint name="wrist" type="hinge" axis="1 0 0" range="-3.2 3.2"/>\n'
        f'              <geom name="cutter_head" group="3" type="box" size="0.022 0.016 0.008"'
        f' pos="0 0.016 0" material="steel"/>\n'
        f'              <site name="{CUTTER_SITE}" pos="0 0.030 0" size="0.005" rgba="1 0.3 0.3 0.9"/>\n'
        # Wrist camera, set back and above the cutter so it sees the berry it is
        # approaching. The wrist is held level by the tray coupling, so the
        # horizon does not roll.
        f'              <camera name="{WRIST_CAM}" pos="0 -0.035 0.055"'
        f' xyaxes="1 0 0 0 0.38 1" fovy="58"/>\n'
        # The tray rides below the cutter, so a cut berry lands in it — if the
        # approach put it there. Geometry decides, not a lookup table.
        #
        # Rolling resistance lives on the tray, not on the fruit. With MuJoCo's
        # default contact an ellipsoid rolls like a ball bearing, and a cut
        # berry rolled off the open side of the tray under the gentlest
        # deceleration; a real strawberry, conical and wearing its calyx, does
        # not. MuJoCo takes the richer contact of the two geoms, so this gives
        # berry-on-tray contacts rolling friction and leaves the cutter's
        # contacts with attached fruit exactly as the force thresholds were
        # calibrated. Putting it on the berry instead raised the force on an
        # attached berry by half again and turned near misses into torn stems.
        f'              <geom name="{TRAY_GEOM}" group="3" type="box" size="0.050 0.055 0.004"'
        f' pos="0 0.030 -0.085" rgba="0.75 0.75 0.78 1"'
        f' condim="6" friction="1.2 0.02 0.01"/>\n'
        f'              <geom name="tray_lip" group="3" type="box" size="0.050 0.004 0.018"'
        f' pos="0 0.089 -0.067" rgba="0.75 0.75 0.78 1"'
        f' condim="6" friction="1.2 0.02 0.01"/>\n'
        f"            </body>\n"
        f"          </body>\n"
        f"        </body>\n"
        f"      </body>\n"
        f"    </body>\n"
    )

    parts.append("  </worldbody>\n  <actuator>\n")
    for joint in ARM_JOINTS:
        parts.append(f'    <position name="a_{joint}" joint="{joint}"/>\n')
    parts.append("  </actuator>\n  <equality>\n")
    for b in scenario.berries:
        # The peduncle. Deactivating this is the cut.
        parts.append(
            f'    <weld name="{b.berry_id}_stem" body1="{b.berry_id}"'
            f' body2="{b.berry_id}_anchor" solref="0.005 1"/>\n'
        )
    parts.append("  </equality>\n</mujoco>\n")
    return "".join(parts)
