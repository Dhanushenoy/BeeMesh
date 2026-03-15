r"""
BeeMesh Task Executor

Routes incoming tasks to the appropriate workload implementation.
Workloads are registered in a simple registry mapping task_type -> function.
"""

from beemesh.workloads.diffusion import run_diffusion_task

# -------------------------------------------------
# Workload registry
# -------------------------------------------------

WORKLOAD_REGISTRY = {
    "diffusion": run_diffusion_task,
}


def execute_task(task: dict):
    """Execute a given task based on its type."""
    task_type = task.get("task_type")
    payload = task.get("payload", {})

    if task_type not in WORKLOAD_REGISTRY:
        raise ValueError(f"Unknown task type: {task_type}")

    workload_fn = WORKLOAD_REGISTRY[task_type]

    return workload_fn(payload)
