from collections import deque

import beemesh.coordinator.scheduler as scheduler
from beemesh.coordinator.scheduler import schedule, worker_can_run_task


def test_dead_worker_is_never_eligible():
    worker = {"status": "dead", "cpu_cores": 4, "ram_gb": 16.0}
    task = {"task_id": "task-1", "task_type": "python_batch", "payload": {}}

    assert worker_can_run_task(worker, task, worker_id="worker-1") is False


def test_target_worker_id_is_respected():
    worker = {"status": "alive", "cpu_cores": 4, "ram_gb": 16.0}
    task = {
        "task_id": "task-1",
        "task_type": "python_batch",
        "payload": {},
        "requirements": {"target_worker_id": "worker-2"},
    }

    assert worker_can_run_task(worker, task, worker_id="worker-1") is False
    assert worker_can_run_task(worker, task, worker_id="worker-2") is True


def test_scarcity_bonus_prefers_specialized_task_for_capable_worker():
    workers = {
        "worker-1": {
            "status": "alive",
            "cpu_cores": 4,
            "ram_gb": 16.0,
            "gpu": None,
            "gpu_memory_gb": 0.0,
            "performance_score": 4.0,
        },
        "worker-2": {
            "status": "alive",
            "cpu_cores": 4,
            "ram_gb": 2.0,
            "gpu": None,
            "gpu_memory_gb": 0.0,
            "performance_score": 4.0,
        },
    }
    queue = deque(
        [
            {"task_id": "generic", "task_type": "python_batch", "payload": {}},
            {
                "task_id": "high-ram",
                "task_type": "python_batch",
                "payload": {},
                "requirements": {"min_ram_gb": 8.0},
            },
        ]
    )

    selected = schedule(queue, "worker-1", workers["worker-1"], workers=workers)

    assert selected is not None
    assert selected["task_id"] == "high-ram"


def test_older_task_gets_priority_when_other_scores_match(monkeypatch):
    worker = {
        "status": "alive",
        "cpu_cores": 4,
        "ram_gb": 8.0,
        "gpu": None,
        "gpu_memory_gb": 0.0,
        "performance_score": 4.0,
    }
    workers = {"worker-1": worker}
    queue = deque(
        [
            {
                "task_id": "newer",
                "task_type": "python_batch",
                "payload": {},
                "enqueued_at": 95.0,
            },
            {
                "task_id": "older",
                "task_type": "python_batch",
                "payload": {},
                "enqueued_at": 0.0,
            },
        ]
    )
    monkeypatch.setattr(scheduler.time, "time", lambda: 100.0)

    selected = schedule(queue, "worker-1", worker, workers=workers)

    assert selected is not None
    assert selected["task_id"] == "older"
