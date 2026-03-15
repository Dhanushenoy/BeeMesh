r"""
BeeMesh Hive State

In-memory coordinator state for the BeeMesh runtime.
This module tracks which bees are known to the hive, which task cells
are waiting to be assigned, and which results have already been stored.

State view:

             .-------------------.
            /   HIVE REGISTRY     \
           / workers | queue |     \
           \ results | ids   |     /
            '-------------------'
               /       |       \
              /        |        \
         [Bee-01]  <task cell>  [Bee-02]
              \        |        /
               \   <result>    /
                    [Bee-03]

Honeycomb mapping:
  - The hive center is the coordinator's in-memory state.
  - Bees register with the hive and pull available task cells.
  - Completed cells return as results and are stored by task ID.
"""

import time
from collections import deque
from typing import Any, Deque, Dict, Optional



class HiveState:
    """
    Central runtime state of the BeeMesh coordinator (Hive).
    """

    def __init__(self):

        # worker_id -> metadata
        self.workers: Dict[str, Dict[str, Any]] = {}

        # worker_id -> active task count
        self.worker_active_tasks: Dict[str, int] = {}

        # pending tasks
        self.task_queue: Deque[Dict[str, Any]] = deque()

        # task_id -> leased task metadata
        self.leased_tasks: Dict[str, Dict[str, Any]] = {}

        # task_id -> result
        self.results: Dict[str, Any] = {}

        self.worker_counter: int = 0

    # -------------------------
    # Worker management
    # -------------------------

    def register_worker(
        self,
        hostname: str,
        cpu_cores: int = 1,
        ram_gb: float = 0.0,
        gpu: Optional[str] = None,
    ) -> str:

        self.worker_counter += 1
        worker_id = f"worker-{self.worker_counter}"

        self.workers[worker_id] = {
            "hostname": hostname,
            "cpu_cores": cpu_cores,
            "ram_gb": ram_gb,
            "gpu": gpu,
            "last_seen": time.time(),
            "status": "alive",
        }

        self.worker_active_tasks[worker_id] = 0

        print(
            f"[Hive] Registered {worker_id} "
            f"(CPU={cpu_cores}, RAM={ram_gb}GB, GPU={gpu})"
        )

        return worker_id

    # -------------------------
    # Task scheduling
    # -------------------------

    def heartbeat(self, worker_id: str) -> bool:
        """Update last-seen time for a worker."""

        if worker_id not in self.workers:
            return False

        self.workers[worker_id]["last_seen"] = time.time()
        self.workers[worker_id]["status"] = "alive"
        return True

    def lease_task(
        self,
        worker_id: str,
        lease_timeout_s: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Lease the next task to a worker for a bounded period."""

        if worker_id not in self.workers:
            return None

        worker = self.workers[worker_id]
        max_tasks = worker.get("cpu_cores", 1)

        active = self.worker_active_tasks.get(worker_id, 0)

        # worker already busy enough
        if active >= max_tasks:
            return None

        if not self.task_queue:
            return None

        task = self.task_queue.popleft()
        leased_at = time.time()

        self.worker_active_tasks[worker_id] += 1
        self.workers[worker_id]["last_seen"] = leased_at
        self.workers[worker_id]["status"] = "alive"
        task["lease_timeout_s"] = lease_timeout_s
        self.leased_tasks[task["task_id"]] = {
            "task": task,
            "worker_id": worker_id,
            "leased_at": leased_at,
            "lease_timeout_s": lease_timeout_s,
        }

        return task

    def get_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Backward-compatible alias for leasing a task."""

        return self.lease_task(worker_id)

    def add_task(self, task: Dict[str, Any]) -> None:
        self.task_queue.append(task)

    def requeue_expired_tasks(self) -> int:
        """Return expired leased tasks back to the queue."""

        now = time.time()
        expired_task_ids = []

        for task_id, lease in self.leased_tasks.items():
            lease_age = now - lease["leased_at"]
            if lease_age > lease["lease_timeout_s"]:
                expired_task_ids.append(task_id)

        for task_id in expired_task_ids:
            lease = self.leased_tasks.pop(task_id)
            worker_id = lease["worker_id"]
            task = lease["task"]
            self.task_queue.appendleft(task)
            if worker_id in self.worker_active_tasks:
                self.worker_active_tasks[worker_id] = max(
                    0, self.worker_active_tasks[worker_id] - 1
                )

        return len(expired_task_ids)

    def mark_worker_dead(self, worker_id: str) -> None:
        """Mark a worker dead and requeue all tasks leased to it."""

        if worker_id not in self.workers:
            return

        self.workers[worker_id]["status"] = "dead"

        task_ids = [
            task_id
            for task_id, lease in self.leased_tasks.items()
            if lease["worker_id"] == worker_id
        ]

        for task_id in task_ids:
            lease = self.leased_tasks.pop(task_id)
            self.task_queue.appendleft(lease["task"])

        self.worker_active_tasks[worker_id] = 0

    def sweep_dead_workers(self, worker_timeout_s: int = 60) -> int:
        """Mark workers dead when they stop sending heartbeats."""

        now = time.time()
        dead_workers = []

        for worker_id, info in self.workers.items():
            if info["status"] == "dead":
                continue
            if now - info["last_seen"] > worker_timeout_s:
                dead_workers.append(worker_id)

        for worker_id in dead_workers:
            self.mark_worker_dead(worker_id)

        return len(dead_workers)

    # -------------------------
    # Result handling
    # -------------------------

    def store_result(self, worker_id: str, task_id: str, result: Any) -> None:

        self.results[task_id] = result
        self.leased_tasks.pop(task_id, None)

        if worker_id in self.worker_active_tasks:
            self.worker_active_tasks[worker_id] = max(
                0, self.worker_active_tasks[worker_id] - 1
            )
        if worker_id in self.workers:
            self.workers[worker_id]["last_seen"] = time.time()
            self.workers[worker_id]["status"] = "alive"
