"""
Visualize results produced by ``examples/parallel_sweep_test/launch.py``.

Usage:
    python examples/parallel_sweep_test/visualize.py --results-dir server_results
"""

import argparse
import json
from pathlib import Path
import re


PATTERN = re.compile(r"(?P<name>[\w-]+)\s*->\s*(?P<value>[-+]?\d+(?:\.\d+)?)")
DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "parallel_cases.json"


def parse_stdout(stdout: str):
    points = []
    for line in stdout.splitlines():
        match = PATTERN.search(line.strip())
        if match:
            points.append((match.group("name"), float(match.group("value"))))
    return points


def extract_points_from_task_results(task_results):
    points = []
    for task_id in sorted(task_results):
        result = task_results[task_id]
        points.extend(parse_stdout(result.get("stdout", "")))
    return points


def load_points(results_dir: Path):
    points = []
    for result_file in sorted(results_dir.rglob("*.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        stdout = payload.get("result", {}).get("stdout", "")
        points.extend(parse_stdout(stdout))
    return points


def load_saved_points(data_file: Path):
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    return [(name, float(value)) for name, value in payload]


def render_plot(points, output_path: Path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Parsed points:")
        for name, value in points:
            print(f"{name}: {value}")
        return

    names = [name for name, _ in points]
    values = [value for _, value in points]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, values, color="#f4b400")
    ax.set_title("BeeMesh Parallel Case Results")
    ax.set_xlabel("Case")
    ax.set_ylabel("Value")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)


def main():
    parser = argparse.ArgumentParser(description="Visualize BeeMesh case outputs.")
    parser.add_argument("--results-dir", default="server_results")
    parser.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "parallel_cases.png"))
    args = parser.parse_args()

    data_file = Path(args.data_file)
    if data_file.exists():
        points = load_saved_points(data_file)
    else:
        points = load_points(Path(args.results_dir))
    if not points:
        raise SystemExit("No case results found.")

    output_path = Path(args.output)
    render_plot(points, output_path)
    print(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
