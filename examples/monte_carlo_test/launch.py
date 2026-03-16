"""
Launch a Monte Carlo style parameter sweep through BeeMesh.

Usage:
    beemesh --launch examples/monte_carlo_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import json
import math
from pathlib import Path
import random

import beemesh


random.seed(42)
samples_input = input("How many samples are needed per case? [ex:5000]: ").strip()
SAMPLES = int(samples_input) if samples_input else 5000

cases = [
    {
        "case_id": idx,
        "mean": mean,
        "sigma": sigma,
        "samples": SAMPLES,
    }
    for idx, (mean, sigma) in enumerate(
        [
            (0.0, 0.5),
            (0.0, 1.0),
            (0.5, 1.0),
            (1.0, 1.5),
            (1.5, 2.0),
            (2.0, 2.5),
            (2.5, 3.0),
            (3.0, 3.5),
        ],
        start=1,
    )
]


def run_case(case):
    draws = [
        random.gauss(case["mean"], case["sigma"]) for _ in range(case["samples"])
    ]
    estimate = sum(math.sin(value) ** 2 for value in draws) / len(draws)
    print(
        f"case={case['case_id']} mean={case['mean']:.2f} "
        f"sigma={case['sigma']:.2f} estimate={estimate:.6f}"
    )


def beemesh_finalize(results_dir=None, task_results=None):
    """Generate a quick sweep plot after the remote launch finishes."""

    if not task_results:
        print("No task results available for plotting.")
        return

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    data_path = data_dir / "monte_carlo_sweep.json"
    raw_results_path = data_dir / "raw_task_results.json"
    plot_path = scenario_dir / "monte_carlo_sweep.png"
    visualize_script = scenario_dir / "visualize.py"

    try:
        from examples.monte_carlo_test.visualize import (
            extract_points_from_task_results,
            render_plot,
        )
    except ImportError:
        print(f"Hive result files: {results_dir}")
        return

    points = extract_points_from_task_results(task_results)
    if not points:
        print("No plottable results found in the returned task payloads.")
        return
    raw_results_path.write_text(json.dumps(task_results, indent=2), encoding="utf-8")
    data_path.write_text(json.dumps(points, indent=2), encoding="utf-8")
    render_plot(points, plot_path)
    if results_dir is not None:
        print(f"Hive result files: {results_dir}")
    print(f"Saved raw task results to {raw_results_path}")
    print(f"Saved parsed data to {data_path}")
    print(f"Saved plot to {plot_path}")
    print(f"Visualize again with: python {visualize_script}")


with beemesh.parallel():
    for case in cases:
        run_case(case)
