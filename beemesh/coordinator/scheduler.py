"""
BeeMesh Scheduler

Responsible for deciding which task should be given to a worker.
This version performs simple capability-aware matching based on
CPU, RAM, GPU, and current worker load.
"""

from __future__ import annotations

from typing import Any, Deque, Dict, Optional


def _task_requirements(task: Dict[str, Any]) -> Dict[str, Any]:
    """Return normalized task requirements."""

    return dict(task.get("requirements") or {})


def worker_can_run_task(
    worker: Dict[str, Any],
    task: Dict[str, Any],
    worker_id: Optional[str] = None,
) -> bool:
    """Return True when the worker satisfies the task's hard requirements."""

    requirements = _task_requirements(task)
    if not requirements:
        return True

    if worker.get("status") != "alive":
        return False

    target_worker_id = requirements.get("target_worker_id")
    if target_worker_id and worker_id != target_worker_id:
        return False

    min_cpu = int(requirements.get("min_cpu_cores", 0) or 0)
    if int(worker.get("cpu_cores", 0) or 0) < min_cpu:
        return False

    min_ram = float(requirements.get("min_ram_gb", 0.0) or 0.0)
    if float(worker.get("ram_gb", 0.0) or 0.0) < min_ram:
        return False

    requires_gpu = bool(requirements.get("requires_gpu", False))
    has_gpu = bool(worker.get("gpu"))
    if requires_gpu and not has_gpu:
        return False

    min_gpu_memory = float(requirements.get("min_gpu_memory_gb", 0.0) or 0.0)
    if min_gpu_memory > 0.0 and float(worker.get("gpu_memory_gb", 0.0) or 0.0) < min_gpu_memory:
        return False

    preferred_arch = requirements.get("architecture")
    if preferred_arch and worker.get("architecture") != preferred_arch:
        return False

    return True


def score_worker_for_task(
    worker: Dict[str, Any],
    active_tasks: int,
    task: Dict[str, Any],
) -> float:
    """Score how suitable a worker is for a task after hard filtering."""

    requirements = _task_requirements(task)

    score = 0.0
    score += float(worker.get("cpu_cores", 1) or 1) * 1.5
    score += float(worker.get("ram_gb", 0.0) or 0.0) * 0.35
    score += float(worker.get("gpu_memory_gb", 0.0) or 0.0) * 0.5
    score -= active_tasks * 2.0

    preferred_device = requirements.get("preferred_device", "cpu")
    if preferred_device == "gpu" and worker.get("gpu"):
        score += 8.0
    elif preferred_device == "gpu":
        score -= 4.0

    estimated_cost = float(requirements.get("estimated_cost", 1.0) or 1.0)
    score += min(estimated_cost, 10.0) * float(worker.get("performance_score", 1.0))

    if requirements.get("requires_gpu") and worker.get("gpu"):
        score += 5.0

    return score


def schedule(
    task_queue: Deque[Dict[str, Any]],
    worker_id: str,
    worker: Dict[str, Any],
    active_tasks: int = 0,
) -> Optional[Dict[str, Any]]:
    """Return and remove the best task for the given worker."""

    if not task_queue:
        return None

    best_index = None
    best_score = None
    for index, task in enumerate(task_queue):
        if not worker_can_run_task(worker, task, worker_id=worker_id):
            continue

        score = score_worker_for_task(worker, active_tasks, task)
        if best_score is None or score > best_score:
            best_score = score
            best_index = index

    if best_index is None:
        return None

    if best_index == 0:
        return task_queue.popleft()

    selected = task_queue[best_index]
    del task_queue[best_index]
    return selected
