"""
Visualize results produced by ``beemesh launch ./simulate_case --sweep ...``.

Usage:
    python examples/cpp_exec_test/visualize.py
"""

import argparse
import json
from pathlib import Path


DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "executable_sweep.json"
DEFAULT_BENCHMARK_FILE = Path(__file__).resolve().parent / "data" / "benchmark_runs.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "cpp_exec_scaling.png"


def load_points(data_file: Path):
    return json.loads(data_file.read_text(encoding="utf-8"))


def load_benchmark_runs(data_file: Path):
    return json.loads(data_file.read_text(encoding="utf-8"))


def render_scaling_plot(runs, output_path: Path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Benchmark runs:")
        for run in runs:
            print(run)
        return output_path

    runs = sorted(runs, key=lambda item: (item["bee_count"], item["duration_s"]))
    x = [run["bee_count"] for run in runs]
    y = [run["duration_s"] for run in runs]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(x, y, marker="o", color="#c46b08", linewidth=1.4)
    for run in runs:
        ax.annotate(
            f"{run['duration_s']:.2f}s",
            (run["bee_count"], run["duration_s"]),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=8,
        )
    ax.set_title("BeeMesh C++ Runtime vs Number of Bees")
    ax.set_xlabel("Number of Bees")
    ax.set_ylabel("Runtime (s)")
    ax.set_xticks(sorted(set(x)))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Visualize BeeMesh C++ sweep results.")
    parser.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--benchmark-file", default=str(DEFAULT_BENCHMARK_FILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    benchmark_file = Path(args.benchmark_file)
    if benchmark_file.exists():
        runs = load_benchmark_runs(benchmark_file)
        if not runs:
            raise SystemExit("No benchmark runs found.")
        output_path = render_scaling_plot(runs, Path(args.output))
        print(f"Saved plot to {output_path}")
        return

    points = load_points(Path(args.data_file))
    if not points:
        raise SystemExit("No executable sweep results found.")

    print("Parsed sweep points:")
    for point in points:
        print(point)
    output_path = Path(args.output)
    print(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
