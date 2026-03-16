"""
Launch a simple case-parallel script through BeeMesh.

Usage:
    beemesh --launch examples/parallel_sweep_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import importlib.util
import json
from pathlib import Path

import beemesh


cases = [
    {"name": "case-a", "value": 1},
    {"name": "case-b", "value": 2},
    {"name": "case-c", "value": 3},
    {"name": "case-d", "value": 4},
]


def run_case(case):
    result = case["value"] ** 2
    print(f"{case['name']} -> {result}")


def _load_visualize_module():
    """Load the sibling visualize module without depending on repo import paths."""

    module_path = Path(__file__).resolve().parent / "visualize.py"
    spec = importlib.util.spec_from_file_location("beemesh_parallel_visualize", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load visualize module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def beemesh_finalize(results_dir=None, task_results=None):
    """Generate a quick plot after the remote launch finishes."""

    if not task_results:
        print("No task results available for plotting.")
        return

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    data_path = data_dir / "parallel_cases.json"
    raw_results_path = data_dir / "raw_task_results.json"
    plot_path = scenario_dir / "parallel_cases.png"
    visualize_script = scenario_dir / "visualize.py"

    try:
        visualize = _load_visualize_module()
    except ImportError:
        print(f"Hive result files: {results_dir}")
        return

    points = visualize.extract_points_from_task_results(task_results)
    if not points:
        print("No plottable results found in the returned task payloads.")
        return
    raw_results_path.write_text(json.dumps(task_results, indent=2), encoding="utf-8")
    data_path.write_text(json.dumps(points, indent=2), encoding="utf-8")
    visualize.render_plot(points, plot_path)
    if results_dir is not None:
        print(f"Hive result files: {results_dir}")
    print(f"Saved raw task results to {raw_results_path}")
    print(f"Saved parsed data to {data_path}")
    print(f"Saved plot to {plot_path}")
    print(f"Visualize again with: python {visualize_script}")


with beemesh.parallel():
    for case in cases:
        run_case(case)
