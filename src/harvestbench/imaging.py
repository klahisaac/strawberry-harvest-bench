"""Writing a PNG without a third-party imaging library.

The bench writes the occasional frame — the one perception read, a close-up
of a scene — and that is a handful of images. A dependency on Pillow to write a dozen PNGs is not
worth it when the format's uncompressed-RGB case is this small.
"""

import struct
import zlib
from pathlib import Path

import numpy as np


def write_png(path: Path, rgb: np.ndarray, level: int = 6) -> Path:
    """Write an (h, w, 3) uint8 array as a PNG."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected (h, w, 3), got {rgb.shape}")
    arr = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w, _ = arr.shape
    # Each scanline is prefixed with a filter byte; 0 means "no filter".
    raw = np.hstack([np.zeros((h, 1), np.uint8), arr.reshape(h, w * 3)]).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level))
        + chunk(b"IEND", b"")
    )
    return path


def read_png(path: Path) -> np.ndarray:
    """Read back a PNG this module wrote: 8-bit RGB, no interlace, filter 0.

    Not a general decoder: frames written by `write_png` are all it reads.
    """
    raw = Path(path).read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    i, idat, w, h = 8, b"", 0, 0
    while i < len(raw):
        (n,) = struct.unpack(">I", raw[i : i + 4])
        tag, body = raw[i + 4 : i + 8], raw[i + 8 : i + 8 + n]
        if tag == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", body[:10])
            if (depth, colour) != (8, 2):
                raise ValueError(f"{path}: only 8-bit RGB is supported")
        elif tag == b"IDAT":
            idat += body
        i += 12 + n
    rows = np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, w * 3 + 1)
    if rows[:, 0].any():
        raise ValueError(f"{path}: filtered scanlines are not supported")
    return rows[:, 1:].reshape(h, w, 3).copy()


def downscale(rgb: np.ndarray, factor: int) -> np.ndarray:
    """Box-average by an integer factor. Keeps the file small for the web."""
    if factor <= 1:
        return rgb
    h, w, c = rgb.shape
    h, w = h - h % factor, w - w % factor
    block = rgb[:h, :w].reshape(h // factor, factor, w // factor, factor, c)
    return block.mean(axis=(1, 3)).round().astype(np.uint8)
