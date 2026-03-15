"""
BeeMesh Diffusion Workload

A small 2D diffusion solver used as the first scientific workload for BeeMesh. 
This is intentionally simple and serves as the first distributed PDE example.
"""

import numpy as np


def run_diffusion_task(payload: dict):
    """
    Execute a small 2D diffusion solver task.

    Expected payload keys:
       nx, ny - grid dimensions
       steps - number of time steps to run
       alpha - diffusion coefficient

    Returns:
        Dictionary with summary statistics that can be sent back to the Hive.
    """
    nx = payload.get("nx", 64)
    ny = payload.get("ny", 64)
    steps = payload.get("steps", 100)
    alpha = payload.get("alpha", 0.1)

    if nx <= 0 or ny <= 0:
        raise ValueError("Diffusion task requires positive 'nx' and 'ny' values.")
    if steps < 0:
        raise ValueError("Diffusion task requires a non-negative 'steps' value.")

    # Initialize the grid with some initial condition (e.g., a hot spot in the center)
    u = np.zeros((nx, ny), dtype=np.float32)
    u[nx // 2, ny // 2] = 1.0  # Initial hot spot

    for _ in range(steps):
        u_new = u.copy()
        u_new[1:-1, 1:-1] = u[1:-1, 1:-1] + alpha * (
            u[2:, 1:-1]
            + u[:-2, 1:-1]
            + u[1:-1, 2:]
            + u[1:-1, :-2]
            - 4 * u[1:-1, 1:-1]
        )
        u = u_new

    return {
        "nx": nx,
        "ny": ny,
        "steps": steps,
        "alpha": alpha,
        "mean": float(np.mean(u)),
        "max": float(np.max(u)),
        "min": float(np.min(u)),
    }
