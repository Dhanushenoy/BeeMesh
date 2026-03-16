"""
Launch a 2D moving-wave advection demo with tiled ghost exchange.

Usage:
    beemesh --launch examples/advection_grid_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import json
from pathlib import Path

import beemesh
import numpy as np


nx_input = input("Grid nx? [128]: ").strip()
ny_input = input("Grid ny? [128]: ").strip()
steps_input = input("Number of Euler steps? [80]: ").strip()

nx = int(nx_input) if nx_input else 128
ny = int(ny_input) if ny_input else 128
steps = int(steps_input) if steps_input else 80

x = np.linspace(0.0, 1.0, nx, endpoint=False)
y = np.linspace(0.0, 1.0, ny, endpoint=False)
xx, yy = np.meshgrid(x, y, indexing="ij")
u = np.exp(-((xx - 0.25) ** 2 + (yy - 0.5) ** 2) / 0.01)

c_x = 0.6
c_y = 0.25
dx = 1.0 / nx
dy = 1.0 / ny
dt = 0.25 * min(dx / max(abs(c_x), 1e-8), dy / max(abs(c_y), 1e-8))

beemesh_grid_workload = "advection2d"
beemesh_snapshot_interval = max(1, steps // 10)


def beemesh_finalize(
    results_dir=None,
    final_grid=None,
    step_history=None,
    frame_snapshots=None,
    tile_partitions=None,
):
    """Save the final field, dump frame PNGs, and build an animation."""

    if final_grid is None:
        print("No final grid available.")
        return

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    frames_dir = data_dir / "pic"
    frames_dir.mkdir(exist_ok=True)
    field_path = data_dir / "final_field.json"
    history_path = data_dir / "step_history.json"
    frames_path = data_dir / "frame_snapshots.json"
    partitions_path = data_dir / "tile_partitions.json"
    plot_path = scenario_dir / "advection_final.png"
    gif_path = scenario_dir / "advection_evolution.gif"
    visualize_script = scenario_dir / "visualize.py"

    field_path.write_text(json.dumps(np.asarray(final_grid).tolist()), encoding="utf-8")
    history_path.write_text(json.dumps(step_history or [], indent=2), encoding="utf-8")
    frame_payload = [
        {"step": frame["step"], "field": np.asarray(frame["field"]).tolist()}
        for frame in (frame_snapshots or [])
    ]
    frames_path.write_text(json.dumps(frame_payload), encoding="utf-8")
    partitions_path.write_text(json.dumps(tile_partitions or {}, indent=2), encoding="utf-8")

    try:
        from examples.advection_grid_test.visualize import render_field, render_gif
    except ImportError:
        if results_dir is not None:
            print(f"Hive result files: {results_dir}")
        return

    x_parts = []
    y_parts = []
    if tile_partitions:
        x_parts = tile_partitions.get("x_parts", [])
        y_parts = tile_partitions.get("y_parts", [])

    for index, frame in enumerate(frame_snapshots or []):
        frame_file = frames_dir / f"frame_{index:03d}.png"
        render_field(
            np.asarray(frame["field"]),
            frame_file,
            step=frame["step"],
            x_parts=x_parts,
            y_parts=y_parts,
        )

    output_path = render_field(
        np.asarray(final_grid),
        plot_path,
        step=(step_history or [{}])[-1].get("step", 0),
        x_parts=x_parts,
        y_parts=y_parts,
    )
    gif_output = render_gif(frames_dir, gif_path)
    if results_dir is not None:
        print(f"Hive result files: {results_dir}")
    print(f"Saved final field to {field_path}")
    print(f"Saved step history to {history_path}")
    print(f"Saved frame metadata to {frames_path}")
    print(f"Saved tile partitions to {partitions_path}")
    print(f"Saved frame PNGs to {frames_dir}")
    print(f"Saved plot to {output_path}")
    if gif_output is not None:
        print(f"Saved GIF to {gif_output}")
    print(f"Visualize again with: python {visualize_script}")


with beemesh.parallel(grid=u):
    for step in range(steps):
        u = u
