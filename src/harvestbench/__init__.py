"""Simulation-first bench for an autonomous strawberry-harvesting robot."""

import os

# The bench renders, and it renders on machines with no display. MuJoCo's own
# default picks a windowed backend and fails there, so EGL is chosen unless the
# caller has already said otherwise. This has to happen before mujoco loads.
os.environ.setdefault("MUJOCO_GL", "egl")

# Physics always runs on the CPU; only the cameras touch the GPU, which is the
# default. HARVEST_RENDER=cpu pins EGL to Mesa's software rasterizer (llvmpipe)
# for machines with no usable GPU. The two renderers do not produce identical
# pixels, so a baseline only gates exactly against runs on the renderer it was
# recorded with. Every value is a setdefault, so an explicit environment wins.
_MESA_EGL_VENDOR = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"

if (
    os.environ.get("HARVEST_RENDER", "gpu").lower() == "cpu"
    and os.environ["MUJOCO_GL"] == "egl"
    and os.path.exists(_MESA_EGL_VENDOR)
):
    # Hide the NVIDIA EGL vendor so glvnd can only hand out Mesa devices.
    os.environ.setdefault("__EGL_VENDOR_LIBRARY_FILENAMES", _MESA_EGL_VENDOR)
    # On an Intel or AMD GPU Mesa itself drives the hardware; force software.
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    # Mesa warns when software is forced on an explicitly chosen device, once
    # per worker. Failures still raise in Python, so silence the warning only.
    os.environ.setdefault("EGL_LOG_LEVEL", "fatal")
