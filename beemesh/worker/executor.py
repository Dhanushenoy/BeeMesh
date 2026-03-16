r"""
BeeMesh Task Executor

Routes incoming tasks to the appropriate workload implementation.
Workloads are registered in a simple registry mapping task_type -> function.
"""

from beemesh.workloads.advection_tile import run_advection_tile_task
from beemesh.workloads.diffusion import run_diffusion_task
from beemesh.workloads.executable_batch import run_executable_batch_task
from beemesh.workloads.python_batch import run_python_batch_task

# -------------------------------------------------
# Workload registry
# -------------------------------------------------

WORKLOAD_REGISTRY = {
    "advection_tile": run_advection_tile_task,
    "diffusion": run_diffusion_task,
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
