"""
Visualize results produced by ``examples/mandelbrot_test/launch.py``.

Usage:
    python examples/mandelbrot_test/visualize.py
"""

import argparse
import json
from pathlib import Path


PREFIX = "TILE_JSON "
DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "mandelbrot_tiles.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "mandelbrot.png"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "server_results"


def parse_stdout(stdout: str):
    tiles = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(PREFIX):
            payload = json.loads(line[len(PREFIX) :])
            tiles.append(payload)
    return tiles


def extract_tiles_from_task_results(task_results):
    tiles = []
    for task_id in sorted(task_results):
        result = task_results[task_id]
        tiles.extend(parse_stdout(result.get("stdout", "")))
    return sorted(tiles, key=lambda item: item["tile_id"])


def load_tiles(results_dir: Path):
    tiles = []
    for result_file in sorted(results_dir.rglob("*.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        stdout = payload.get("result", {}).get("stdout", "")
        tiles.extend(parse_stdout(stdout))
    return sorted(tiles, key=lambda item: item["tile_id"])


def load_saved_tiles(data_file: Path):
    return json.loads(data_file.read_text(encoding="utf-8"))


def assemble_image(tiles):
    if not tiles:
        return [], 0, 0, 0

    width = max(tile["x1"] for tile in tiles)
    height = max(tile["y1"] for tile in tiles)
    max_iter = max(tile["max_iter"] for tile in tiles)
    image = [[0 for _ in range(width)] for _ in range(height)]

    for tile in tiles:
        for row_offset, row in enumerate(tile["values"]):
            y = tile["y0"] + row_offset
            image[y][tile["x0"] : tile["x1"]] = row

    return image, width, height, max_iter


def write_pgm(image, output_path: Path, max_iter: int):
    pgm_path = output_path.with_suffix(".pgm")
    height = len(image)
    width = len(image[0]) if height else 0
    max_value = 255
    lines = [f"P2\n{width} {height}\n{max_value}\n"]
    scale = max(max_iter, 1)
    for row in image:
        values = [str(int(255 * value / scale)) for value in row]
        lines.append(" ".join(values))
        lines.append("\n")
    pgm_path.write_text("".join(lines), encoding="utf-8")
    return pgm_path


def render_plot(tiles, output_path: Path):
    image, width, height, max_iter = assemble_image(tiles)
    if not image or width == 0 or height == 0:
        raise ValueError("No image data available to render.")

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        fallback_path = write_pgm(image, output_path, max_iter)
        print(f"matplotlib not installed. Wrote grayscale fallback to {fallback_path}")
        return fallback_path

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(image, cmap="inferno", origin="lower")
    ax.set_title("BeeMesh Distributed Mandelbrot Render")
    ax.set_xlabel("Pixel X")
    ax.set_ylabel("Pixel Y")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Visualize BeeMesh Mandelbrot tile outputs."
    )
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    data_file = Path(args.data_file)
    if data_file.exists():
        tiles = load_saved_tiles(data_file)
    else:
        tiles = load_tiles(Path(args.results_dir))
    if not tiles:
        raise SystemExit("No Mandelbrot tile results found.")

    output_path = Path(args.output)
    final_path = render_plot(tiles, output_path)
    print(f"Saved render to {final_path}")


if __name__ == "__main__":
    main()
