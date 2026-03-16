import time

import pytest

from beemesh.coordinator.state import HiveState


def test_add_task_rejects_duplicate_task_ids():
    state = HiveState()
    task = {"task_id": "task-1", "task_type": "python_batch", "payload": {}}

    state.add_task(task)

    with pytest.raises(ValueError, match="already queued"):
        state.add_task(task.copy())


def test_lease_and_store_result_update_state_consistently():
    state = HiveState()
    worker_id = state.register_worker("bee-1", cpu_cores=2, ram_gb=8.0)
    state.add_task({"task_id": "task-1", "task_type": "python_batch", "payload": {}})

    leased = state.lease_task(worker_id, lease_timeout_s=15)

    assert leased is not None
    assert leased["task_id"] == "task-1"
    assert "task-1" in state.leased_tasks
    assert state.worker_active_tasks[worker_id] == 1

    state.store_result(worker_id, "task-1", {"success": True})

    assert state.results["task-1"] == {"success": True}
    assert "task-1" not in state.leased_tasks
    assert state.worker_active_tasks[worker_id] == 0


def test_store_result_rejects_wrong_worker():
    state = HiveState()
    worker_1 = state.register_worker("bee-1", cpu_cores=1, ram_gb=4.0)
    worker_2 = state.register_worker("bee-2", cpu_cores=1, ram_gb=4.0)
    state.add_task({"task_id": "task-1", "task_type": "python_batch", "payload": {}})
    state.lease_task(worker_1)

    with pytest.raises(ValueError, match="leased to"):
        state.store_result(worker_2, "task-1", {"success": False})


def test_requeue_expired_tasks_returns_task_to_queue():
    state = HiveState()
    worker_id = state.register_worker("bee-1", cpu_cores=1, ram_gb=4.0)
    state.add_task({"task_id": "task-1", "task_type": "python_batch", "payload": {}})
    state.lease_task(worker_id, lease_timeout_s=1)
    state.leased_tasks["task-1"]["leased_at"] = time.time() - 5

    expired = state.requeue_expired_tasks()

    assert expired == 1
    assert "task-1" not in state.leased_tasks
    assert state.task_queue[0]["task_id"] == "task-1"
    assert state.worker_active_tasks[worker_id] == 0


def test_mark_worker_dead_requeues_all_leased_tasks():
    state = HiveState()
    worker_id = state.register_worker("bee-1", cpu_cores=2, ram_gb=8.0)
    state.add_task({"task_id": "task-1", "task_type": "python_batch", "payload": {}})
    state.add_task({"task_id": "task-2", "task_type": "python_batch", "payload": {}})
    state.lease_task(worker_id)
    state.lease_task(worker_id)

    state.mark_worker_dead(worker_id)

    assert state.workers[worker_id]["status"] == "dead"
    assert state.worker_active_tasks[worker_id] == 0
    assert len(state.leased_tasks) == 0
    assert {task["task_id"] for task in state.task_queue} == {"task-1", "task-2"}
