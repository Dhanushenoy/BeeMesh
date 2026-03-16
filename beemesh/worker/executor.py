r"""
BeeMesh Task Executor

Worker-side dispatch layer for BeeMesh task execution.

The Bee receives generic task dictionaries from the Hive. This module maps the
task's ``task_type`` to a local workload implementation and executes it using
the task payload. New built-in workload types are registered here.
"""

from beemesh.workloads.pde_timestep_tile import run_pde_timestep_tile_task
from beemesh.workloads.executable_batch import run_executable_batch_task
from beemesh.workloads.python_batch import run_python_batch_task

# -------------------------------------------------
# Workload registry
# -------------------------------------------------

WORKLOAD_REGISTRY = {
    "pde_timestep_tile": run_pde_timestep_tile_task,
    "executable_batch": run_executable_batch_task,
    "python_batch": run_python_batch_task,
}


def execute_task(task: dict):
    """Execute a given task based on its type."""
    task_type = task.get("task_type")
    payload = task.get("payload", {})

    if task_type not in WORKLOAD_REGISTRY:
        raise ValueError(f"Unknown task type: {task_type}")

    workload_fn = WORKLOAD_REGISTRY[task_type]

    return workload_fn(payload)
