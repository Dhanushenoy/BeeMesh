"""
Visualize results produced by ``examples/nn_hyperparam_test/launch.py``.

Usage:
    python examples/nn_hyperparam_test/visualize.py --results-dir server_results
"""

import argparse
import json
from pathlib import Path
import re


PATTERN = re.compile(
    r"trial=(?P<trial>\d+)\s+hidden=(?P<hidden>\d+)\s+lr=(?P<lr>[-+]?\d+(?:\.\d+)?)\s+"
    r"epochs=(?P<epochs>\d+)\s+val_acc=(?P<acc>[-+]?\d+(?:\.\d+)?)\s+val_loss=(?P<loss>[-+]?\d+(?:\.\d+)?)"
)
DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "data" / "nn_hyperparam_search.json"


def parse_stdout(stdout: str):
    points = []
    for line in stdout.splitlines():
        match = PATTERN.search(line.strip())
        if match:
            points.append(
                {
                    "trial": int(match.group("trial")),
                    "hidden": int(match.group("hidden")),
                    "lr": float(match.group("lr")),
                    "epochs": int(match.group("epochs")),
                    "acc": float(match.group("acc")),
                    "loss": float(match.group("loss")),
                }
            )
    return points


def extract_points_from_task_results(task_results):
    points = []
    for task_id in sorted(task_results):
        result = task_results[task_id]
        points.extend(parse_stdout(result.get("stdout", "")))
    return sorted(points, key=lambda item: item["trial"])


def load_points(results_dir: Path):
    points = []
    for result_file in sorted(results_dir.rglob("*.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        stdout = payload.get("result", {}).get("stdout", "")
        points.extend(parse_stdout(stdout))
    return sorted(points, key=lambda item: item["trial"])


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

    hidden = [point["hidden"] for point in points]
    learning_rates = [point["lr"] for point in points]
    accuracies = [point["acc"] for point in points]

    fig, ax = plt.subplots(figsize=(8, 5))
    scatter = ax.scatter(
        hidden,
        learning_rates,
        c=accuracies,
        cmap="plasma",
        s=[120 + 200 * acc for acc in accuracies],
        alpha=0.85,
    )
    for point in points:
        ax.annotate(
            f"{point['acc']:.3f}",
            (point["hidden"], point["lr"]),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=8,
        )
    ax.set_title("BeeMesh NN Hyperparameter Search")
    ax.set_xlabel("Hidden Layer Width")
    ax.set_ylabel("Learning Rate")
    ax.grid(alpha=0.25)
    fig.colorbar(scatter, ax=ax, label="Validation Accuracy")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)


def main():
    parser = argparse.ArgumentParser(
        description="Visualize BeeMesh neural-network sweep outputs."
    )
    parser.add_argument("--results-dir", default="server_results")
    parser.add_argument("--data-file", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "nn_hyperparam_search.png"))
    args = parser.parse_args()

    data_file = Path(args.data_file)
    if data_file.exists():
        points = load_saved_points(data_file)
    else:
        points = load_points(Path(args.results_dir))
    if not points:
        raise SystemExit("No neural-network sweep results found.")

    output_path = Path(args.output)
    render_plot(points, output_path)
    print(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
