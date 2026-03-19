"""
BeeMesh workload for one structured-grid PDE timestep on a ghosted tile.

This worker-side kernel advances one tile of a periodic structured field. The
same task type currently supports:
- explicit linear advection of a scalar field
- a simple periodic acoustic pulse / wave-equation pressure update

The Hive/client sends one ghosted tile (and any auxiliary state) plus the
numerical parameters for a single explicit timestep. The worker advances only
the tile interior and returns updated interior values and simple statistics.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np


def _run_advection_tile(payload: Dict[str, Any], ghost: int) -> Dict[str, Any]:
    """Advance one ghosted scalar tile by one forward-Euler advection step."""

    tile = np.asarray(payload["tile"], dtype=np.float64)
    c_x = float(payload["c_x"])
    c_y = float(payload["c_y"])
    dx = float(payload["dx"])
    dy = float(payload["dy"])
    dt = float(payload["dt"])
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
        "interior": updated,
        "mean": float(np.mean(updated)),
        "max": float(np.max(updated)),
        "min": float(np.min(updated)),
    }


def _run_acoustic_tile(payload: Dict[str, Any], ghost: int) -> Dict[str, Any]:
    """Advance one periodic acoustic-pressure tile with a simple wave update."""

    pressure = np.asarray(payload["tile"], dtype=np.float64)
    prev_pressure = np.asarray(payload["prev_tile"], dtype=np.float64)
    wave_speed = float(payload["wave_speed"])
    dx = float(payload["dx"])
    dy = float(payload["dy"])
    dt = float(payload["dt"])

    interior = pressure[ghost:-ghost, ghost:-ghost]
    prev_interior = prev_pressure[ghost:-ghost, ghost:-ghost]
    left = pressure[:-2, 1:-1]
    right = pressure[2:, 1:-1]
    down = pressure[1:-1, :-2]
    up = pressure[1:-1, 2:]

    laplacian = (left - 2.0 * interior + right) / (dx * dx)
    laplacian += (down - 2.0 * interior + up) / (dy * dy)
    updated = 2.0 * interior - prev_interior + (wave_speed * dt) ** 2 * laplacian

    return {
        "interior": updated,
        "mean": float(np.mean(updated)),
        "max": float(np.max(updated)),
        "min": float(np.min(updated)),
    }


def run_pde_timestep_tile_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Advance one ghosted tile for the requested structured-grid PDE update."""

    ghost = int(payload.get("ghost", 1))
    if ghost != 1:
        raise ValueError("PDE tile workload currently supports ghost width 1 only.")

    workload = payload.get("grid_workload", "advection2d")
    if workload == "advection2d":
        result = _run_advection_tile(payload, ghost)
    elif workload == "acoustic_pulse2d":
        result = _run_acoustic_tile(payload, ghost)
    else:
        raise ValueError(f"Unsupported structured-grid workload '{workload}'.")

    return {
        "step_index": int(payload["step_index"]),
        "tile_x": int(payload["tile_x"]),
        "tile_y": int(payload["tile_y"]),
        "x0": int(payload["x0"]),
        "x1": int(payload["x1"]),
        "y0": int(payload["y0"]),
        "y1": int(payload["y1"]),
        "interior": result["interior"].tolist(),
        "mean": result["mean"],
        "max": result["max"],
        "min": result["min"],
    }
