"""
Launch a tiled Mandelbrot render through BeeMesh.

Usage:
    beemesh --launch examples/mandelbrot_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import json
from pathlib import Path

import beemesh

_LIVE_PREVIEW_STATE = {"fig": None, "ax": None, "image": None}

width_input = input("Image width in pixels? [640]: ").strip()
height_input = input("Image height in pixels? [360]: ").strip()
max_iter_input = input("Max iterations per pixel? [100]: ").strip()
tiles_x_input = input("Tiles along x? [4]: ").strip()
tiles_y_input = input("Tiles along y? [3]: ").strip()

WIDTH = int(width_input) if width_input else 640
HEIGHT = int(height_input) if height_input else 360
MAX_ITER = int(max_iter_input) if max_iter_input else 100
TILES_X = int(tiles_x_input) if tiles_x_input else 4
TILES_Y = int(tiles_y_input) if tiles_y_input else 3

X_MIN = -2.2
X_MAX = 1.0
Y_MIN = -1.2
Y_MAX = 1.2

tile_width = WIDTH // TILES_X
tile_height = HEIGHT // TILES_Y

cases = []
tile_id = 1
for tile_y in range(TILES_Y):
    for tile_x in range(TILES_X):
        x0 = tile_x * tile_width
        x1 = WIDTH if tile_x == TILES_X - 1 else (tile_x + 1) * tile_width
        y0 = tile_y * tile_height
        y1 = HEIGHT if tile_y == TILES_Y - 1 else (tile_y + 1) * tile_height
        cases.append(
            {
                "tile_id": tile_id,
                "tile_x": tile_x,
                "tile_y": tile_y,
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "width": WIDTH,
                "height": HEIGHT,
                "max_iter": MAX_ITER,
                "x_min": X_MIN,
                "x_max": X_MAX,
                "y_min": Y_MIN,
                "y_max": Y_MAX,
            }
        )
        tile_id += 1


def run_tile(case):
    rows = []
    for py in range(case["y0"], case["y1"]):
        imag = case["y_min"] + (py / max(case["height"] - 1, 1)) * (
            case["y_max"] - case["y_min"]
        )
        row = []
        for px in range(case["x0"], case["x1"]):
            real = case["x_min"] + (px / max(case["width"] - 1, 1)) * (
                case["x_max"] - case["x_min"]
            )
            z_real = 0.0
            z_imag = 0.0
            iteration = 0
            while z_real * z_real + z_imag * z_imag <= 4.0 and iteration < case["max_iter"]:
                next_real = z_real * z_real - z_imag * z_imag + real
                z_imag = 2.0 * z_real * z_imag + imag
                z_real = next_real
                iteration += 1
            row.append(iteration)
        rows.append(row)

    tile_payload = {
        "tile_id": case["tile_id"],
        "tile_x": case["tile_x"],
        "tile_y": case["tile_y"],
        "x0": case["x0"],
        "x1": case["x1"],
        "y0": case["y0"],
        "y1": case["y1"],
        "width": case["width"],
        "height": case["height"],
        "max_iter": case["max_iter"],
        "values": rows,
    }
    print(f"TILE_JSON {json.dumps(tile_payload, separators=(',', ':'))}")


def beemesh_task_requirements(batch):
    """Prefer GPU-capable bees for Mandelbrot tiles, but allow CPU fallback."""

    total_pixels = sum(
        (item["x1"] - item["x0"]) * (item["y1"] - item["y0"]) for item in batch
    )
    max_iter = max(item["max_iter"] for item in batch)
    estimated_cost = max(2.0, round(total_pixels * max_iter / 250000.0, 2))
    return {
        "preferred_device": "gpu",
        "min_cpu_cores": 1,
        "min_ram_gb": 0.5,
        "estimated_cost": estimated_cost,
    }


def _render_tiles(task_results, output_path: Path):
    from examples.mandelbrot_test.visualize import (
        extract_tiles_from_task_results,
        render_plot,
    )

    tiles = extract_tiles_from_task_results(task_results)
    if not tiles:
        return None, 0
    final_path = render_plot(tiles, output_path)
    return final_path, len(tiles)


def beemesh_live_update(results_dir=None, task_results=None, pending_tasks=None):
    """Update a partial render while tile results are still arriving."""

    if not task_results:
        return

    scenario_dir = Path(__file__).resolve().parent
    preview_path = scenario_dir / "mandelbrot_live.png"
    try:
        from examples.mandelbrot_test.visualize import (
            assemble_image,
            extract_tiles_from_task_results,
            render_plot,
        )
    except ImportError:
        return

    tiles = extract_tiles_from_task_results(task_results)
    if not tiles:
        return

    image, _, _, _ = assemble_image(tiles)

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        final_path = render_plot(tiles, preview_path)
    else:
        plt.ion()
        fig = _LIVE_PREVIEW_STATE["fig"]
        ax = _LIVE_PREVIEW_STATE["ax"]
        image_artist = _LIVE_PREVIEW_STATE["image"]

        if fig is None or ax is None or image_artist is None:
            fig, ax = plt.subplots(figsize=(10, 6))
            image_artist = ax.imshow(image, cmap="inferno", origin="lower")
            ax.set_title("BeeMesh Live Mandelbrot Preview")
            ax.set_xlabel("Pixel X")
            ax.set_ylabel("Pixel Y")
            fig.tight_layout()
            _LIVE_PREVIEW_STATE["fig"] = fig
            _LIVE_PREVIEW_STATE["ax"] = ax
            _LIVE_PREVIEW_STATE["image"] = image_artist
        else:
            image_artist.set_data(image)

        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        plt.pause(0.001)
        fig.savefig(preview_path, dpi=180)
        final_path = preview_path

    if pending_tasks is None:
        pending_tasks = 0
    print(
        f"Live preview updated: {final_path} "
        f"({len(tiles)} tile(s) assembled, {pending_tasks} pending)"
    )


def beemesh_finalize(results_dir=None, task_results=None):
    """Assemble the rendered tiles and save a final image locally."""

    if not task_results:
        print("No task results available for plotting.")
        return

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    raw_results_path = data_dir / "raw_task_results.json"
    data_path = data_dir / "mandelbrot_tiles.json"
    plot_path = scenario_dir / "mandelbrot.png"
    visualize_script = scenario_dir / "visualize.py"

    raw_results_path.write_text(json.dumps(task_results, indent=2), encoding="utf-8")

    try:
        from examples.mandelbrot_test.visualize import extract_tiles_from_task_results
    except ImportError:
        if results_dir is not None:
            print(f"Hive result files: {results_dir}")
        return

    tiles = extract_tiles_from_task_results(task_results)
    if not tiles:
        print("No Mandelbrot tile payloads were found in the returned task results.")
        return

    data_path.write_text(json.dumps(tiles, indent=2), encoding="utf-8")
    final_path, _ = _render_tiles(task_results, plot_path)

    if results_dir is not None:
        print(f"Hive result files: {results_dir}")
    print(f"Saved raw task results to {raw_results_path}")
    print(f"Saved parsed tile data to {data_path}")
    print(f"Saved render to {final_path}")
    print(f"Visualize again with: python {visualize_script}")


with beemesh.parallel():
    for case in cases:
        run_tile(case)
