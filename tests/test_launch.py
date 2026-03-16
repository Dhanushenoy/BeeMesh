from pathlib import Path

import pytest

from beemesh.launch import (
    _task_requirements_for_batch,
    _weighted_worker_strips,
    extract_parallel_spec,
    preflight_worker_fit,
)


def test_extract_parallel_spec_supports_swarm_alias(tmp_path):
    script = tmp_path / "swarm_example.py"
    script.write_text(
        "\n".join(
            [
                "import beemesh",
                "cases = [1, 2, 3]",
                "",
                "with beemesh.swarm():",
                "    for case in cases:",
                "        print(case * 2)",
            ]
        ),
        encoding="utf-8",
    )

    spec = extract_parallel_spec(str(script))

    assert spec.iterable_expr == "cases"
    assert spec.loop_target == "case"
    assert "print(case * 2)" in spec.loop_body


def test_task_requirements_hook_overrides_defaults():
    namespace = {
        "beemesh_task_requirements": lambda batch: {
            "min_ram_gb": float(len(batch)),
            "estimated_cost": 9.5,
        }
    }

    requirements = _task_requirements_for_batch(namespace, [1, 2, 3])

    assert requirements["preferred_device"] == "cpu"
    assert requirements["min_cpu_cores"] == 1
    assert requirements["min_ram_gb"] == 3.0
    assert requirements["estimated_cost"] == 9.5


def test_preflight_worker_fit_rejects_unschedulable_tasks():
    workers = {
        "worker-1": {
            "status": "alive",
            "cpu_cores": 4,
            "ram_gb": 8.0,
            "gpu": None,
            "gpu_memory_gb": 0.0,
            "architecture": "x86_64",
            "performance_score": 4.0,
        }
    }
    tasks = [
        {
            "task_id": "gpu-task",
            "task_type": "python_batch",
            "payload": {},
            "requirements": {"requires_gpu": True},
        }
    ]

    with pytest.raises(RuntimeError, match="no eligible bee"):
        preflight_worker_fit(tasks, workers)


def test_weighted_worker_strips_biases_larger_ranges_to_stronger_workers():
    workers = {
        "worker-1": {"status": "alive", "performance_score": 10.0},
        "worker-2": {"status": "alive", "performance_score": 2.0},
    }

    strips = _weighted_worker_strips(12, workers)

    assert strips[0][0] == "worker-1"
    assert strips[0][2] - strips[0][1] > strips[1][2] - strips[1][1]
    assert strips[-1][2] == 12
