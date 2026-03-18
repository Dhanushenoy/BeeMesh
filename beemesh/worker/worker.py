r"""
BeeMesh Worker (Bee)

Runtime loop for a Bee worker.

A Bee registers with the Hive, reports basic hardware capabilities, polls for
leased tasks, executes them locally, sends heartbeats while running, and
submits results back to the coordinator.

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
import platform
import threading
import time
import traceback

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
        task_poll_interval: float = 1.0,
        request_timeout: float = 30.0,
        reconnect_interval: float = 5.0,
    ):
        self.hostname = hostname
        self.hive_url = hive_url.rstrip("/")
        self.auth_token = auth_token
        self.heartbeat_interval = heartbeat_interval
        self.task_poll_interval = task_poll_interval
        self.request_timeout = request_timeout
        self.reconnect_interval = reconnect_interval
        self.worker_id = None
        self._connection_lost = False

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
        gpu_memory_gb = 0.0
        architecture = platform.machine() or None

        return {
            "cpu_cores": cpu_cores,
            "ram_gb": ram_gb,
            "gpu": gpu,
            "gpu_memory_gb": gpu_memory_gb,
            "architecture": architecture,
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
                "gpu_memory_gb": cap["gpu_memory_gb"],
                "architecture": cap["architecture"],
                "auth_token": self.auth_token,
            },
            timeout=self.request_timeout,
        )
        r.raise_for_status()

        data = r.json()
        self.worker_id = data["worker_id"]

        print(f"Registered with Hive as {self.worker_id}")
        print(
            f"[{self.worker_id}] CPU={cap['cpu_cores']} cores | "
            f"RAM={cap['ram_gb']} GB | GPU={cap['gpu']} | "
            f"GPU_MEM={cap['gpu_memory_gb']} GB | ARCH={cap['architecture']}"
        )
        self._mark_connection_restored()

    def _mark_connection_lost(self):
        """Log a connection loss once until Hive communication recovers."""

        if self._connection_lost:
            return
        self._connection_lost = True
        target = self.worker_id or self.hostname
        print(
            f"[{target}] Lost connection to Hive at {self.hive_url}. "
            f"Retrying every {self.reconnect_interval:.1f}s..."
        )

    def _mark_connection_restored(self):
        """Log when Hive communication recovers after a failure."""

        if self._connection_lost:
            target = self.worker_id or self.hostname
            print(f"[{target}] Reconnected to Hive.")
        self._connection_lost = False

    # --------------------------------------------------
    # Task request (long polling)
    # --------------------------------------------------

    def request_task(self, timeout=30):
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
                timeout=self.request_timeout,
            )
            r.raise_for_status()
            self._mark_connection_restored()

            data = r.json()
            task = data.get("task")

            if task is not None:
                return task

            if time.time() - start_time > timeout:
                return None

            time.sleep(self.task_poll_interval)

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
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        self._mark_connection_restored()

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
            timeout=min(self.request_timeout, 15),
        )
        response.raise_for_status()
        self._mark_connection_restored()

    def _heartbeat_loop(self):
        """Send heartbeats in the background for remote workers."""

        while True:
            try:
                self.send_heartbeat()
            except requests.RequestException:
                self._mark_connection_lost()
            time.sleep(self.heartbeat_interval)

    # --------------------------------------------------
    # Worker main loop
    # --------------------------------------------------

    def run(self):
        """Main worker loop."""

        self.register()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        while True:
            try:
                task = self.request_task(timeout=self.request_timeout)
            except requests.RequestException:
                self._mark_connection_lost()
                time.sleep(self.reconnect_interval)
                continue

            if task is None:
                time.sleep(2)
                continue

            print(f"[{self.worker_id}] Running task {task['task_id']}")

            try:
                result = execute_task(task)
            except Exception as exc:
                result = {
                    "success": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            while True:
                try:
                    self.submit_result(task["task_id"], result)
                    break
                except requests.RequestException:
                    self._mark_connection_lost()
                    time.sleep(self.reconnect_interval)


# --------------------------------------------------
# Local execution
# --------------------------------------------------

if __name__ == "__main__":
    worker = BeeWorker(hostname="local-bee")
    worker.run()
