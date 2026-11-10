"""Damped least squares inverse kinematics for the arm.

The solve is position only, over a subset of the joints. The rest are dependent:
a `couple` function fills them in from the free ones before every forward
evaluation, so the model the solver sees matches how the arm is actually driven.

The cell uses that to keep the catch tray level. What it deliberately does not
do is orient the cutter along the peduncle — the baseline comes in head-on, and
fixing that is the improvement the bench exists to measure.
"""

from collections.abc import Callable

import mujoco
import numpy as np


class ArmIK:
    def __init__(
        self,
        model: mujoco.MjModel,
        site: str,
        joints: tuple[str, ...],
        free: tuple[int, ...] | None = None,
        couple: Callable[[np.ndarray], None] | None = None,
    ):
        self.model = model
        self.scratch = mujoco.MjData(model)
        mujoco.mj_resetData(model, self.scratch)
        self.site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site)
        jids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j) for j in joints]
        self.qadr = np.array([model.jnt_qposadr[j] for j in jids])
        self.dofadr = np.array([model.jnt_dofadr[j] for j in jids])
        self.lo = model.jnt_range[jids, 0].copy()
        self.hi = model.jnt_range[jids, 1].copy()
        self.free = np.array(free if free is not None else range(len(joints)))
        self.couple = couple
        self._jacp = np.zeros((3, model.nv))
        self._jacr = np.zeros((3, model.nv))

    def forward(self, q: np.ndarray) -> np.ndarray:
        """Cutter position for a joint vector, after applying the coupling."""
        if self.couple is not None:
            self.couple(q)
        np.clip(q, self.lo, self.hi, out=q)
        d = self.scratch
        d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, d)
        mujoco.mj_comPos(self.model, d)
        return d.site_xpos[self.site_id].copy()

    def solve(
        self,
        q0: np.ndarray,
        target: np.ndarray,
        iters: int = 200,
        damping: float = 0.06,
        tol: float = 5e-4,
        step_limit: float = 0.2,
    ) -> tuple[np.ndarray, float]:
        """Joint vector that puts the cutter at target, and the residual error."""
        q = np.asarray(q0, dtype=float).copy()
        target = np.asarray(target, dtype=float)
        free_dofs = self.dofadr[self.free]
        err_norm = float("inf")
        for _ in range(iters):
            err = target - self.forward(q)
            err_norm = float(np.linalg.norm(err))
            if err_norm < tol:
                break
            mujoco.mj_jacSite(self.model, self.scratch, self._jacp, self._jacr, self.site_id)
            jac = self._jacp[:, free_dofs]
            # (J Jᵀ + λ²I) y = err, then dq = Jᵀ y
            lhs = jac @ jac.T + (damping**2) * np.eye(3)
            dq = jac.T @ np.linalg.solve(lhs, err)
            norm = np.linalg.norm(dq)
            if norm > step_limit:
                dq *= step_limit / norm
            q[self.free] += dq
            np.clip(q, self.lo, self.hi, out=q)
        self.forward(q)  # leave q consistent with the coupling
        return q, err_norm
