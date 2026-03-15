r"""
BeeMesh Worker (Bee)

A Bee registers with the Hive, pulls task cells from the Hive, executes them,
and submits results back to the colony.

Honeybee taking a task:
        _  _
       | )/ )
    \\ |//,' __
    (")(_)-"()))=-
       (\\
    -----------
    |  task   |
    -----------  

Flow:
  [Bee] -- request_task --> [Hive]
  [Bee] <-- TaskResponse -- [Hive]
  [Bee] -- execute + submit_result --> [Hive]
"""

import os
import threading
import time

import requests

from beemesh.worker.executor import execute_task

DEFAULT_HIVE_URL = os.getenv("BEEMESH_HIVE_URL", "http://127.0.0.1:8000")
DEFAULT_AUTH_TOKEN = os.getenv("BEEMESH_AUTH_TOKEN", "")


class BeeWorker:
    """
    Worker bee that registers with the Hive, pulls tasks, executes them,
    and submits results.
    """

    def __init__(
        self,
        hostname: str,
        hive_url: str = DEFAULT_HIVE_URL,
        auth_token: str = DEFAULT_AUTH_TOKEN,
        heartbeat_interval: float = 10.0,
    ):
        self.hostname = hostname
        self.hive_url = hive_url.rstrip("/")
        self.auth_token = auth_token
        self.heartbeat_interval = heartbeat_interval
        self.worker_id = None

    # --------------------------------------------------
    # Capability detection
    # --------------------------------------------------

    def detect_capabilities(self):
        """Detect basic hardware capabilities of this worker."""

        cpu_cores = os.cpu_count() or 1

        try:
            import psutil

            ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
        except Exception:
            ram_gb = 0.0

        gpu = None  # placeholder for future GPU detection

        return {
            "cpu_cores": cpu_cores,
            "ram_gb": ram_gb,
            "gpu": gpu,
        }

    # --------------------------------------------------
    # Registration
    # --------------------------------------------------

    def register(self):
        """Register this worker with the Hive."""

        cap = self.detect_capabilities()

        r = requests.post(
            f"{self.hive_url}/register_worker",
            json={
                "hostname": self.hostname,
                "cpu_cores": cap["cpu_cores"],
                "ram_gb": cap["ram_gb"],
                "gpu": cap["gpu"],
                "auth_token": self.auth_token,
            },
            timeout=30,
        )
        r.raise_for_status()

        data = r.json()
        self.worker_id = data["worker_id"]

        print(f"Registered with Hive as {self.worker_id}")
        print(
            f"[{self.worker_id}] CPU={cap['cpu_cores']} cores | RAM={cap['ram_gb']} GB | GPU={cap['gpu']}"
        )

    # --------------------------------------------------
    # Task request (long polling)
    # --------------------------------------------------

    def request_task(self, timeout=30, poll_interval=0.5):
        """
        Long-poll the Hive for a task.
        The worker keeps asking for a task for up to `timeout` seconds
        before giving up and returning None.
        """

        start_time = time.time()

        while True:
            r = requests.post(
                f"{self.hive_url}/request_task",
                json={
                    "worker_id": self.worker_id,
                    "auth_token": self.auth_token,
                },
                timeout=30,
            )
            r.raise_for_status()

            data = r.json()
            task = data.get("task")

            if task is not None:
                return task

            if time.time() - start_time > timeout:
                return None

            time.sleep(poll_interval)

    # --------------------------------------------------
    # Submit result
    # --------------------------------------------------

    def submit_result(self, task_id, result):
        """Send completed task result back to the Hive."""

        response = requests.post(
            f"{self.hive_url}/submit_result",
            json={
                "worker_id": self.worker_id,
                "task_id": task_id,
                "result": result,
                "auth_token": self.auth_token,
            },
            timeout=30,
        )
        response.raise_for_status()

    def send_heartbeat(self):
        """Tell the Hive that this worker is still alive."""

        if self.worker_id is None:
            return

        response = requests.post(
            f"{self.hive_url}/heartbeat",
            json={
                "worker_id": self.worker_id,
                "auth_token": self.auth_token,
            },
            timeout=15,
        )
        response.raise_for_status()

    def _heartbeat_loop(self):
        """Send heartbeats in the background for remote workers."""

        while True:
            try:
                self.send_heartbeat()
            except requests.RequestException:
                pass
            time.sleep(self.heartbeat_interval)

    # --------------------------------------------------
    # Worker main loop
    # --------------------------------------------------

    def run(self):
        """Main worker loop."""

        self.register()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        while True:
            task = self.request_task()

            if task is None:
                time.sleep(2)
                print(f"[{self.worker_id}] No tasks received after waiting, retrying...")
                continue

            print(f"[{self.worker_id}] Running task {task['task_id']}")

            result = execute_task(task)
            for attempt in range(5):
                try:
                    self.submit_result(task["task_id"], result)
                    break
                except requests.RequestException:
                    if attempt == 4:
                        raise
                    time.sleep(2)


# --------------------------------------------------
# Local execution
# --------------------------------------------------

if __name__ == "__main__":
    worker = BeeWorker(hostname="local-bee")
    worker.run()
