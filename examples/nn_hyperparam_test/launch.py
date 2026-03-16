"""
Launch a simple neural-network hyperparameter search through BeeMesh.

Usage:
    beemesh --launch examples/nn_hyperparam_test/launch.py --hive-url http://127.0.0.1:8000 --auth-token <client-token>
"""

import json
from pathlib import Path

import beemesh
import numpy as np


epochs_input = input("How many epochs per trial? [40]: ").strip()
EPOCHS = int(epochs_input) if epochs_input else 40

trials = [
    {"trial_id": idx, "hidden_dim": hidden_dim, "learning_rate": learning_rate, "epochs": EPOCHS}
    for idx, (hidden_dim, learning_rate) in enumerate(
        [
            (4, 0.02),
            (4, 0.05),
            (8, 0.02),
            (8, 0.05),
            (12, 0.01),
            (12, 0.02),
            (16, 0.01),
            (16, 0.02),
        ],
        start=1,
    )
]


def make_dataset():
    rng = np.random.default_rng(7)
    n = 320
    x = rng.normal(size=(n, 2))
    boundary = x[:, 0] * x[:, 1] + 0.35 * x[:, 0] - 0.2 * x[:, 1]
    y = (boundary > 0.15).astype(np.float64).reshape(-1, 1)
    split = int(0.8 * n)
    return x[:split], y[:split], x[split:], y[split:]


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def run_trial(trial):
    x_train, y_train, x_val, y_val = make_dataset()
    rng = np.random.default_rng(100 + trial["trial_id"])

    hidden_dim = trial["hidden_dim"]
    lr = trial["learning_rate"]
    epochs = trial["epochs"]

    w1 = rng.normal(scale=0.35, size=(2, hidden_dim))
    b1 = np.zeros((1, hidden_dim))
    w2 = rng.normal(scale=0.35, size=(hidden_dim, 1))
    b2 = np.zeros((1, 1))

    for _ in range(epochs):
        z1 = x_train @ w1 + b1
        a1 = np.tanh(z1)
        z2 = a1 @ w2 + b2
        y_hat = sigmoid(z2)

        dz2 = y_hat - y_train
        dw2 = (a1.T @ dz2) / len(x_train)
        db2 = np.mean(dz2, axis=0, keepdims=True)

        da1 = dz2 @ w2.T
        dz1 = da1 * (1.0 - np.tanh(z1) ** 2)
        dw1 = (x_train.T @ dz1) / len(x_train)
        db1 = np.mean(dz1, axis=0, keepdims=True)

        w2 -= lr * dw2
        b2 -= lr * db2
        w1 -= lr * dw1
        b1 -= lr * db1

    val_logits = np.tanh(x_val @ w1 + b1) @ w2 + b2
    val_probs = sigmoid(val_logits)
    val_pred = (val_probs >= 0.5).astype(np.float64)
    val_acc = float(np.mean(val_pred == y_val))
    val_loss = float(
        -np.mean(y_val * np.log(val_probs + 1e-8) + (1 - y_val) * np.log(1 - val_probs + 1e-8))
    )

    print(
        f"trial={trial['trial_id']} hidden={hidden_dim} lr={lr:.3f} "
        f"epochs={epochs} val_acc={val_acc:.4f} val_loss={val_loss:.4f}"
    )


def beemesh_task_requirements(batch):
    """Bias NN search toward workers with enough RAM for NumPy-heavy trials."""

    max_hidden = max(item["hidden_dim"] for item in batch)
    max_epochs = max(item["epochs"] for item in batch)
    estimated_cost = max(2.0, round(len(batch) * max_hidden * max_epochs / 160.0, 2))
    min_ram_gb = 2.0 if max_hidden <= 8 else 4.0
    return {
        "preferred_device": "cpu",
        "min_cpu_cores": 4,
        "min_ram_gb": min_ram_gb,
        "estimated_cost": estimated_cost,
    }


def beemesh_finalize(results_dir=None, task_results=None):
    """Generate a summary plot after the remote launch finishes."""

    if not task_results:
        print("No task results available for plotting.")
        return

    scenario_dir = Path(__file__).resolve().parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    data_path = data_dir / "nn_hyperparam_search.json"
    raw_results_path = data_dir / "raw_task_results.json"
    plot_path = scenario_dir / "nn_hyperparam_search.png"
    visualize_script = scenario_dir / "visualize.py"

    try:
        from examples.nn_hyperparam_test.visualize import (
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
    for trial in trials:
        run_trial(trial)
