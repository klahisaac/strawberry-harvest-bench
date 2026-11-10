"""Rendering the cell's cameras: colour, depth, and segmentation.

Three things come out of the same scene. Colour is what a detector gets.
Depth turns a pixel into a 3D point. Segmentation is the label, free of charge
— the simulator already knows which geom every pixel belongs to, so there is
nothing to annotate and no dataset to license.

Debug annotations are switched off for every render. The cut points are drawn
as sites, and a detector that could see them would be reading the answer off
the picture.
"""

from dataclasses import dataclass

import mujoco
import numpy as np


def _clean_option() -> mujoco.MjvOption:
    """Scene options with the simulator's own annotations hidden."""
    opt = mujoco.MjvOption()
    opt.sitegroup[:] = 0  # cut-point markers
    opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = False
    opt.flags[mujoco.mjtVisFlag.mjVIS_CONSTRAINT] = False
    opt.flags[mujoco.mjtVisFlag.mjVIS_COM] = False
    opt.flags[mujoco.mjtVisFlag.mjVIS_JOINT] = False
    opt.flags[mujoco.mjtVisFlag.mjVIS_CAMERA] = False
    opt.flags[mujoco.mjtVisFlag.mjVIS_LIGHT] = False
    return opt


@dataclass(frozen=True)
class Intrinsics:
    """Pinhole parameters for a MuJoCo camera."""

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def of(cls, model: mujoco.MjModel, camera: str, width: int, height: int) -> "Intrinsics":
        cam = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        fovy = float(model.cam_fovy[cam])
        fy = (height / 2) / np.tan(np.radians(fovy) / 2)
        return cls(width, height, fy, fy, width / 2, height / 2)


def pixel_to_world(
    u: np.ndarray, v: np.ndarray, depth: np.ndarray, intr: Intrinsics,
    cam_pos: np.ndarray, cam_mat: np.ndarray,
) -> np.ndarray:
    """Camera pixels plus depth to world points.

    MuJoCo cameras use the OpenGL convention: x right, y up, looking down -z.
    Image rows run downward, so v is negated.
    """
    x = (u - intr.cx) * depth / intr.fx
    y = -(v - intr.cy) * depth / intr.fy
    z = -depth
    local = np.stack([x, y, z], axis=-1)
    return cam_pos + local @ cam_mat.T


def camera_pose(model: mujoco.MjModel, data: mujoco.MjData, camera: str):
    cam = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
    return data.cam_xpos[cam].copy(), data.cam_xmat[cam].reshape(3, 3).copy()


@dataclass
class Frame:
    """One observation from a camera."""

    rgb: np.ndarray  # (h, w, 3) uint8
    depth: np.ndarray  # (h, w) float, metres
    seg: np.ndarray  # (h, w) int, geom id per pixel, -1 for background
    camera: str

    @property
    def shape(self) -> tuple[int, int]:
        return self.rgb.shape[:2]

    def mask(self, geom_ids) -> np.ndarray:
        return np.isin(self.seg, list(geom_ids))


class CameraRig:
    """A renderer kept alive across frames.

    Building one costs an OpenGL context, so it is created once per size and
    reused. Anything that renders in a loop needs this.
    """

    def __init__(self, model: mujoco.MjModel, width: int = 320, height: int = 240):
        self.model = model
        self.width, self.height = width, height
        self._renderer = mujoco.Renderer(model, height, width)
        self._opt = _clean_option()

    def close(self) -> None:
        self._renderer.close()

    def capture(
        self,
        data: mujoco.MjData,
        camera: str,
        hide: tuple[str, ...] = (),
        hide_groups: tuple[int, ...] = (),
    ) -> Frame:
        """Colour, depth and segmentation from one camera at the current state.

        `hide` names geoms to make invisible for this render only, which is how
        occlusion gets measured: render the fruit with the leaves gone, and the
        ratio of visible pixels is a real number instead of a guess.
        """
        opt = self._opt
        if hide_groups:
            opt = _clean_option()
            for g in hide_groups:
                opt.geomgroup[g] = 0
        restore = []
        for name in hide:
            gid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)
            if gid < 0:
                continue
            restore.append((gid, self.model.geom_rgba[gid].copy()))
            self.model.geom_rgba[gid] = (0, 0, 0, 0)
        try:
            r = self._renderer
            r.update_scene(data, camera=camera, scene_option=opt)
            rgb = r.render().copy()

            r.enable_depth_rendering()
            r.update_scene(data, camera=camera, scene_option=opt)
            depth = r.render().copy()
            r.disable_depth_rendering()

            r.enable_segmentation_rendering()
            r.update_scene(data, camera=camera, scene_option=opt)
            seg = r.render().copy()
            r.disable_segmentation_rendering()
        finally:
            for gid, rgba in restore:
                self.model.geom_rgba[gid] = rgba

        # Segmentation comes back as (h, w, 2): object id and object type.
        ids = seg[:, :, 0].astype(np.int32)
        types = seg[:, :, 1].astype(np.int32)
        ids[types != int(mujoco.mjtObj.mjOBJ_GEOM)] = -1
        return Frame(rgb=rgb, depth=depth, seg=ids, camera=camera)
