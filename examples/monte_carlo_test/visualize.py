"""
Visualize results produced by ``examples/monte_carlo_test/launch.py``.

Usage:
    python examples/monte_carlo_test/visualize.py
"""

import argparse
import json
from pathlib import Path
import re


PATTERN = re.compile(
    r"case=(?P<case_id>\d+)\s+mean=(?P<mean>[-+]?\d+(?:\.\d+)?)\s+"
    r"sigma=(?P<sigma>[-+]?\d+(?:\.\d+)?)\s+estimate=(?P<estimate>[-+]?\d+(?:\.\d+)?)"
)
DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "monte_carlo_sweep.json"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "server_results"


def parse_stdout(stdout: str):
    points = []
    for line in stdout.splitlines():
        match = PATTERN.search(line.strip())
        if match:
            points.append(
                {
                    "case_id": int(match.group("case_id")),
                    "mean": float(match.group("mean")),
                    "sigma": float(match.group("sigma")),
                    "estimate": float(match.group("estimate")),
                }
            )
    return points


def extract_points_from_task_results(task_results):
    points = []
    for task_id in sorted(task_results):
        result = task_results[task_id]
        points.extend(parse_stdout(result.get("stdout", "")))
    return sorted(points, key=lambda item: item["case_id"])


def load_points(results_dir: Path):
    points = []
    for result_file in sorted(results_dir.rglob("*.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        stdout = payload.get("result", {}).get("stdout", "")
        points.extend(parse_stdout(stdout))
    return sorted(points, key=lambda item: item["case_id"])


def load_saved_points(data_file: Path):
    return json.loads(data_file.read_text(encoding="utf-8"))


def render_plot(points, output_path: Path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Parsed points:")
        for point in points:
            print(point)
        return

    sigmas = [point["sigma"] for point in points]
    estimates = [point["estimate"] for point in points]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    scatter = ax.scatter(sigmas, estimates, c=estimates, cmap="viridis", s=90)
    ax.plot(sigmas, estimates, color="#3367d6", alpha=0.5)
    ax.set_title("BeeMesh Monte Carlo Parameter Sweep")
    ax.set_xlabel("Sigma")
    ax.set_ylabel("Estimated Mean(sin(x)^2)")
    ax.grid(alpha=0.25)
    fig.colorbar(scatter, ax=ax, label="Estimate")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)


def main():
    parser = argparse.ArgumentParser(
        description="Visualize BeeMesh Monte Carlo sweep outputs."
    )
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "monte_carlo_sweep.png"))
    args = parser.parse_args()

    data_file = Path(args.data_file)
    if data_file.exists():
        points = load_saved_points(data_file)
    else:
        points = load_points(Path(args.results_dir))
    if not points:
        raise SystemExit("No Monte Carlo sweep results found.")

    output_path = Path(args.output)
    render_plot(points, output_path)
    print(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
