"""Finding berries in a camera frame.

The baseline is a colour threshold over connected components, and like the
baseline policy it is deliberately rough. It is also a real algorithm reading
real pixels, so its failures are real: it loses pale fruit against the canopy,
merges berries that touch, and reports a centroid pulled off-centre whenever a
leaf covers part of a berry.

Those are the failures a learned detector is supposed to fix, and the bench is
what will say whether it did.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .camera import Intrinsics, pixel_to_world
from .cell import DetectedBerry
from .scenario import BERRY_HEIGHT_RATIO


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hue in degrees, saturation and value in 0..1."""
    a = rgb.astype(np.float32) / 255.0
    mx = a.max(axis=-1)
    mn = a.min(axis=-1)
    span = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hue = np.zeros_like(mx)
    nz = span > 1e-6
    with np.errstate(invalid="ignore", divide="ignore"):
        hr = np.where(mx == r, (g - b) / np.where(nz, span, 1), 0)
        hg = np.where(mx == g, 2 + (b - r) / np.where(nz, span, 1), 0)
        hb = np.where(mx == b, 4 + (r - g) / np.where(nz, span, 1), 0)
    hue = np.where(mx == r, hr, np.where(mx == g, hg, hb)) * 60.0
    hue = np.where(nz, hue % 360.0, 0.0)
    sat = np.where(mx > 1e-6, span / np.where(mx > 1e-6, mx, 1), 0.0)
    return hue, sat, mx


@dataclass
class ColorThresholdDetector:
    """Fruit is whatever is saturated and is not leaf-green.

    Every constant below is hand-set. That is the point: they are the thing a
    learned detector replaces, and the bench measures what replacing them buys.
    """

    name: str = "colour"
    # Leaf-green runs roughly 70-170 degrees of hue. Fruit is everything else
    # that is colourful enough to stand out from the grey arm and gutter.
    green_lo: float = 72.0
    green_hi: float = 175.0
    min_sat: float = 0.38
    min_val: float = 0.12
    min_area_px: int = 40
    max_depth_m: float = 1.6
    # Ripeness is read off hue: red is ripe, yellow-green is not. These two are
    # fitted, not guessed — 70 berries under the reference lighting put the
    # relationship at ripeness = -0.0156 * hue + 0.894, near enough a straight
    # line. Which is also the weakness: the fit holds for the lighting it was
    # taken under, and every scenario lights the row a little differently.
    ripe_hue: float = -6.8
    unripe_hue: float = 57.2
    # A blob holding both clearly red and clearly pale fruit is two berries,
    # not one. A ripe berry with an unripe one touching it — or hanging in
    # front of it — otherwise comes out as a single blob whose median hue
    # calls the pair unripe, and the ripe berry is never even attempted.
    # Both populations have to be substantial: a single berry's achene marks
    # are yellow too, and splitting every blob by colour moved the detections
    # in 36 of the 40 full-tier scenarios. Split this way, it moves none.
    red_below_hue: float = 20.0
    pale_above_hue: float = 45.0
    split_min_px: int = 40
    split_min_share: float = 0.2

    def detect(
        self, frame, intr: Intrinsics, cam_pos: np.ndarray, cam_mat: np.ndarray
    ) -> list[DetectedBerry]:
        hue, sat, val = rgb_to_hsv(frame.rgb)
        not_green = (hue < self.green_lo) | (hue > self.green_hi)
        near = np.isfinite(frame.depth) & (frame.depth < self.max_depth_m)
        mask = not_green & (sat > self.min_sat) & (val > self.min_val) & near

        # Opening knocks out the speckle marks and the canopy's lighter flecks.
        mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
        labels, n = ndimage.label(mask)
        blobs = []
        for i in range(1, n + 1):
            blobs += self._split_ripe_from_unripe(labels == i, hue)
        out = []
        for blob in blobs:
            area = int(blob.sum())
            if area < self.min_area_px:
                continue
            ys, xs = np.nonzero(blob)
            # Depth at the blob's core, which is less biased than the mean when
            # a leaf clips an edge.
            d = float(np.median(frame.depth[ys, xs]))
            if not np.isfinite(d) or d <= 0:
                continue
            cu, cv = float(xs.mean()), float(ys.mean())
            surface = pixel_to_world(
                np.array(cu), np.array(cv), np.array(d), intr, cam_pos, cam_mat
            )

            # Size from the blob's extent, converted through depth.
            half_w_px = (xs.max() - xs.min() + 1) / 2
            half_h_px = (ys.max() - ys.min() + 1) / 2
            radius = float(half_w_px * d / intr.fx)
            half_height = float(half_h_px * d / intr.fy)
            # A clipped blob reads short. Fall back to the species ratio when
            # the measured height is implausible for the measured width.
            if half_height < radius:
                half_height = radius * BERRY_HEIGHT_RATIO

            # Depth lands on the near surface, not the centre. Push along the
            # viewing ray by the estimated radius. Left uncorrected this is a
            # systematic ~15 mm bias toward the camera, which the arm then
            # drives into.
            ray = surface - cam_pos
            ray /= max(float(np.linalg.norm(ray)), 1e-9)
            pos = surface + ray * radius

            h = hue[ys, xs]
            # Hue wraps at 360; red sits on both sides of the seam.
            h = np.where(h > 300, h - 360, h)
            mean_hue = float(np.median(h))
            ripeness = float(
                np.clip(
                    (self.unripe_hue - mean_hue) / (self.unripe_hue - self.ripe_hue), 0, 1
                )
            )
            # Compactness against a filled ellipse of the same extent.
            expected = np.pi * half_w_px * half_h_px
            fill = area / expected if expected > 0 else 0.0
            out.append(
                DetectedBerry(
                    berry_id=f"d{len(out):02d}",
                    pos=tuple(float(v) for v in pos),
                    radius=radius,
                    half_height=half_height,
                    ripeness=ripeness,
                    # Nothing here can see how hidden a berry is; a partly
                    # covered blob just looks like a smaller berry.
                    occlusion=0.0,
                    confidence=float(np.clip(fill, 0, 1)),
                )
            )
        return out

    def _split_ripe_from_unripe(self, blob: np.ndarray, hue: np.ndarray) -> list[np.ndarray]:
        """One blob, or two when it is a red berry and a pale one run together."""
        h = hue[blob]
        h = np.where(h > 300, h - 360, h)
        need = max(self.split_min_px, self.split_min_share * h.size)
        red, pale = h < self.red_below_hue, h > self.pale_above_hue
        if red.sum() < need or pale.sum() < need:
            return [blob]
        wrapped = np.where(hue > 300, hue - 360, hue)
        parts = []
        for part in (blob & (wrapped < (self.red_below_hue + self.pale_above_hue) / 2),
                     blob & (wrapped >= (self.red_below_hue + self.pale_above_hue) / 2)):
            part = ndimage.binary_opening(part, structure=np.ones((3, 3)))
            sub, m = ndimage.label(part)
            parts += [sub == j for j in range(1, m + 1)]
        return parts
