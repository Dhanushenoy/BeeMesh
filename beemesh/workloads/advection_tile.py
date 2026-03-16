"""
BeeMesh workload for one Euler step of 2D linear advection on a tile.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np


def run_advection_tile_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Advance one tiled field block by one forward-Euler advection step."""

    tile = np.asarray(payload["tile"], dtype=np.float64)
    c_x = float(payload["c_x"])
    c_y = float(payload["c_y"])
    dx = float(payload["dx"])
    dy = float(payload["dy"])
    dt = float(payload["dt"])
    ghost = int(payload.get("ghost", 1))

    if ghost != 1:
        raise ValueError("Advection tile workload currently supports ghost width 1 only.")

    interior = tile[ghost:-ghost, ghost:-ghost]
    left = tile[:-2, 1:-1]
    right = tile[2:, 1:-1]
    down = tile[1:-1, :-2]
    up = tile[1:-1, 2:]

    if c_x >= 0.0:
        d_dx = (interior - left) / dx
    else:
        d_dx = (right - interior) / dx

    if c_y >= 0.0:
        d_dy = (interior - down) / dy
    else:
        d_dy = (up - interior) / dy

    updated = interior - dt * (c_x * d_dx + c_y * d_dy)

    return {
        "step_index": int(payload["step_index"]),
        "tile_x": int(payload["tile_x"]),
        "tile_y": int(payload["tile_y"]),
        "x0": int(payload["x0"]),
        "x1": int(payload["x1"]),
        "y0": int(payload["y0"]),
        "y1": int(payload["y1"]),
        "interior": updated.tolist(),
        "mean": float(np.mean(updated)),
        "max": float(np.max(updated)),
        "min": float(np.min(updated)),
    }
