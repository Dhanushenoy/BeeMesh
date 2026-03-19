"""
Launch a periodic 2D acoustic pulse demo with tiled ghost exchange.

Usage:
    beemesh launch examples/acoustic_pulse_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import importlib.util
import json
from pathlib import Path

import beemesh
import numpy as np


nx_input = input("Grid nx? [128]: ").strip()
ny_input = input("Grid ny? [128]: ").strip()
steps_input = input("Number of wave steps? [140]: ").strip()
cfl_input = input("Wave CFL safety factor? [0.35]: ").strip()

nx = int(nx_input) if nx_input else 128
ny = int(ny_input) if ny_input else 128
steps = int(steps_input) if steps_input else 140
cfl_safety = float(cfl_input) if cfl_input else 0.35

x = np.linspace(0.0, 1.0, nx, endpoint=False)
y = np.linspace(0.0, 1.0, ny, endpoint=False)
xx, yy = np.meshgrid(x, y, indexing="ij")
x_center = 0.5
y_center = 0.5
p = np.exp(-((xx - x_center) ** 2 + (yy - y_center) ** 2) / 0.006)
beemesh_prev_grid = p.copy()

wave_speed = 1.0
dx = 1.0 / nx
dy = 1.0 / ny
dt = cfl_safety / (wave_speed * np.sqrt((1.0 / (dx * dx)) + (1.0 / (dy * dy))))

beemesh_grid_workload = "acoustic_pulse2d"
beemesh_snapshot_interval = 1


def _load_visualize_module():
    """Load the sibling visualize module without depending on repo import paths."""

    module_path = Path(__file__).resolve().parent / "visualize.py"
    spec = importlib.util.spec_from_file_location("beemesh_acoustic_visualize", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load visualize module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pulse_data(
    final_grid=None,
    step_history=None,
    frame_snapshots=None,
    tile_partitions=None,
):
    """Persist the current pressure field so visualization can be rebuilt later."""

    if final_grid is None:
        return None

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    frames_dir = data_dir / "pic"
    frames_dir.mkdir(exist_ok=True)
    field_path = data_dir / "final_field.json"
    history_path = data_dir / "step_history.json"
    frames_path = data_dir / "frame_snapshots.json"
    partitions_path = data_dir / "tile_partitions.json"

    field_path.write_text(json.dumps(np.asarray(final_grid).tolist()), encoding="utf-8")
    history_path.write_text(json.dumps(step_history or [], indent=2), encoding="utf-8")
    frame_payload = [
        {"step": frame["step"], "field": np.asarray(frame["field"]).tolist()}
        for frame in (frame_snapshots or [])
    ]
    frames_path.write_text(json.dumps(frame_payload), encoding="utf-8")
    partitions_path.write_text(json.dumps(tile_partitions or {}, indent=2), encoding="utf-8")

    return {
        "scenario_dir": scenario_dir,
        "frames_dir": frames_dir,
        "field_path": field_path,
        "history_path": history_path,
        "frames_path": frames_path,
        "partitions_path": partitions_path,
    }


def beemesh_checkpoint(
    results_dir=None,
    final_grid=None,
    step_history=None,
    frame_snapshots=None,
    tile_partitions=None,
):
    """Write partial output during the run so a later crash still leaves plot data."""

    _write_pulse_data(
        final_grid=final_grid,
        step_history=step_history,
        frame_snapshots=frame_snapshots,
        tile_partitions=tile_partitions,
    )


def beemesh_finalize(
    results_dir=None,
    final_grid=None,
    step_history=None,
    frame_snapshots=None,
    tile_partitions=None,
):
    """Save the final pressure field, dump PNGs, and build the animation."""

    if final_grid is None:
        print("No final grid available.")
        return

    paths = _write_pulse_data(
        final_grid=final_grid,
        step_history=step_history,
        frame_snapshots=frame_snapshots,
        tile_partitions=tile_partitions,
    )
    if paths is None:
        print("No final grid available.")
        return

    scenario_dir = paths["scenario_dir"]
    frames_dir = paths["frames_dir"]
    field_path = paths["field_path"]
    history_path = paths["history_path"]
    frames_path = paths["frames_path"]
    partitions_path = paths["partitions_path"]
    plot_path = scenario_dir / "acoustic_pulse_final.png"
    gif_path = scenario_dir / "acoustic_pulse_evolution.gif"
    visualize_script = scenario_dir / "visualize.py"

    try:
        visualize = _load_visualize_module()
    except ImportError:
        if results_dir is not None:
            print(f"Hive result files: {results_dir}")
        return

    x_parts = []
    y_parts = []
    partition_overlays = []
    if tile_partitions:
        x_parts = tile_partitions.get("x_parts", [])
        y_parts = tile_partitions.get("y_parts", [])
        partition_overlays = tile_partitions.get("partition_overlays", [])

    for index, frame in enumerate(frame_snapshots or []):
        frame_file = frames_dir / f"frame_{index:03d}.png"
        visualize.render_field(
            np.asarray(frame["field"]),
            frame_file,
            step=frame["step"],
            x_parts=x_parts,
            y_parts=y_parts,
            partition_overlays=partition_overlays,
            step_history=step_history,
        )

    output_path = visualize.render_field(
        np.asarray(final_grid),
        plot_path,
        step=(step_history or [{}])[-1].get("step", 0),
        x_parts=x_parts,
        y_parts=y_parts,
        partition_overlays=partition_overlays,
        step_history=step_history,
    )
    gif_output = visualize.render_gif(frames_dir, gif_path)
    mp4_output = visualize.render_mp4(
        frames_dir,
        scenario_dir / "acoustic_pulse_evolution.mp4",
    )
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
    if mp4_output is not None:
        print(f"Saved MP4 to {mp4_output}")
    print(f"Visualize again with: python {visualize_script}")


with beemesh.parallel(grid=p):
    for step in range(steps):
        p = p
