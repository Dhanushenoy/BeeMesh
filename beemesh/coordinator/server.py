r"""
BeeMesh Hive Server

FastAPI coordinator for the BeeMesh Hive.

This module provides the worker- and client-facing API surface:
- worker registration, heartbeats, task leasing, and result submission
- client job submission for pre-decomposed task batches
- per-job result persistence on the Hive filesystem
- status and result endpoints for monitoring and launch-side polling

Server bootstrap and API surface:

                 .-~~~~~~~~~~~~~~~~~~~~-.
              .-(   BeeMesh Hive Cloud   )-.
             (    FastAPI app + state       )
              '-._______________________.-'
                        |         |
                 app = FastAPI    state = HiveState()
                        |
         +--------------+--------------+
         |              |              |
   POST /register_worker      POST /request_task
   POST /submit_result        POST /submit_job
         |              |              |
       [Bee]          [Bee]         [Client]

Request flow:

    [Client] ---- submit_job -------> [Hive Cloud API]
    [Bee] ------ register_worker ---> [Hive Cloud API]
    [Bee] ------ request_task ------> [Hive Cloud API]
    [Bee] <----- TaskResponse ------- [Hive Cloud API]
    [Bee] ------ submit_result -----> [Hive Cloud API]
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from beemesh.coordinator.state import HiveState
from beemesh.protocol.models import (
    Heartbeat,
    WorkerRegister,
    WorkerRegisterResponse,
    TaskRequest,
    TaskResponse,
    TaskResult,
    JobSubmit,
)
from beemesh.version import __version__

# FastAPI app instance
app = FastAPI(
    title="BeeMesh Hive",
    version=__version__,
    description="Coordinator API for registering workers, scheduling tasks, and collecting results.",
)

# Global coordinator state (Hive)
state = HiveState()
WORKER_AUTH_TOKEN = os.getenv("BEEMESH_WORKER_TOKEN", "")
CLIENT_AUTH_TOKEN = os.getenv("BEEMESH_CLIENT_TOKEN", WORKER_AUTH_TOKEN)
DEFAULT_LEASE_TIMEOUT_S = int(os.getenv("BEEMESH_LEASE_TIMEOUT", "30"))
DEFAULT_WORKER_TIMEOUT_S = int(os.getenv("BEEMESH_WORKER_TIMEOUT", "60"))
RESULTS_DIR = Path(os.getenv("BEEMESH_RESULTS_DIR", "server_results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# simple job tracking in memory for v0
job_submitted = 0

# Job tracking structures
jobs: Dict[str, Dict[str, Any]] = {}
task_to_job: Dict[str, str] = {}
job_result_roots: Dict[str, Path] = {}


def require_worker_auth(token: Optional[str]) -> None:
    """Validate worker-facing requests when auth is enabled."""

    if WORKER_AUTH_TOKEN and token != WORKER_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid worker auth token")


def require_client_auth(token: Optional[str]) -> None:
    """Validate client job submission when auth is enabled."""

    if CLIENT_AUTH_TOKEN and token != CLIENT_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid client auth token")


def persist_result(
    task_id: str,
    worker_id: str,
    job_id: Optional[str],
    result: Dict[str, Any],
    result_root: Path,
) -> str:
    """Persist a task result on the Hive filesystem and return its path."""

    job_dir = result_root / (job_id or "standalone")
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / f"{task_id}.json"
    payload = {
        "task_id": task_id,
        "worker_id": worker_id,
        "job_id": job_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(result_path)


def resolve_results_root(results_subdir: Optional[str]) -> Path:
    """Resolve a job-specific result root within the Hive workspace."""

    if not results_subdir:
        return RESULTS_DIR

    candidate = Path(results_subdir)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="Invalid results_subdir path.")

    resolved = (Path.cwd() / candidate).resolve()
    return resolved


def validate_tasks_payload(tasks: Any) -> None:
    """Validate manually submitted task payloads before queueing them."""

    if not isinstance(tasks, list) or not tasks:
        raise HTTPException(status_code=400, detail="'tasks' must be a non-empty list.")

    seen_task_ids = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Task at index {index} must be an object.",
            )

        task_id = task.get("task_id")
        task_type = task.get("task_type")
        payload = task.get("payload")
        requirements = task.get("requirements", {})

        if not isinstance(task_id, str) or not task_id:
            raise HTTPException(
                status_code=400,
                detail=f"Task at index {index} is missing a valid 'task_id'.",
            )
        if task_id in seen_task_ids or task_id in task_to_job:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate task_id '{task_id}' in submitted job.",
            )
        seen_task_ids.add(task_id)

        if not isinstance(task_type, str) or not task_type:
            raise HTTPException(
                status_code=400,
                detail=f"Task '{task_id}' is missing a valid 'task_type'.",
            )
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Task '{task_id}' must include an object 'payload'.",
            )
        if requirements is not None and not isinstance(requirements, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Task '{task_id}' has invalid 'requirements'.",
            )

# --------------------------------------------------
# Worker registration
# --------------------------------------------------

@app.post("/register_worker", response_model=WorkerRegisterResponse)
def register_worker(req: WorkerRegister):
    """Register a new Bee (worker) with the Hive"""

    require_worker_auth(req.auth_token)
    worker_id = state.register_worker(
        hostname=req.hostname,
        cpu_cores=req.cpu_cores,
        ram_gb=req.ram_gb,
        gpu=req.gpu,
        gpu_memory_gb=req.gpu_memory_gb,
        architecture=req.architecture,
    )

    return WorkerRegisterResponse(worker_id=worker_id)


# --------------------------------------------------
# Worker requesting a task
# --------------------------------------------------

@app.post("/request_task", response_model=TaskResponse)
def request_task(req: TaskRequest):
    """A Bee (worker) asks the Hive for a task cell."""

    require_worker_auth(req.auth_token)
    state.requeue_expired_tasks()
    state.sweep_dead_workers(DEFAULT_WORKER_TIMEOUT_S)
    task = state.lease_task(req.worker_id, DEFAULT_LEASE_TIMEOUT_S)

    if task is None:
        return TaskResponse(task=None)

    return TaskResponse(task=task)


@app.post("/heartbeat")
def heartbeat(req: Heartbeat):
    """Receive liveness updates from a Bee."""

    require_worker_auth(req.auth_token)
    if not state.heartbeat(req.worker_id):
        raise HTTPException(status_code=404, detail="Unknown worker")
    return {"status": "ok"}


# --------------------------------------------------
# Worker submits result
# --------------------------------------------------

@app.post("/submit_result")
def submit_result(res: TaskResult):
    """A Bee (worker) returns a completed task."""

    require_worker_auth(res.auth_token)
    lease = state.leased_tasks.get(res.task_id)
    if lease is None:
        if res.task_id in state.results:
            raise HTTPException(status_code=409, detail="Task result already submitted.")
        raise HTTPException(status_code=404, detail="Task is not currently leased.")
    if lease["worker_id"] != res.worker_id:
        raise HTTPException(
            status_code=409,
            detail="Task is leased to a different worker.",
        )

    job_id = task_to_job.get(res.task_id)
    result_root = job_result_roots.get(job_id, RESULTS_DIR)
    result_file = persist_result(
        res.task_id,
        res.worker_id,
        job_id,
        res.result,
        result_root,
    )
    enriched_result = dict(res.result)
    enriched_result["__beemesh_result_file__"] = result_file
    enriched_result["__beemesh_worker_id__"] = res.worker_id
    enriched_result["__beemesh_job_id__"] = job_id
    state.store_result(res.worker_id, res.task_id, enriched_result)

    if job_id and job_id in jobs:
        jobs[job_id]["tasks_completed"] += 1

    return {"status": "results stored"}


# --------------------------------------------------
# Submit a new job
# --------------------------------------------------

@app.post("/submit_job")
def submit_job(job: JobSubmit):
    """Submit a new job to the hive."""

    global job_submitted, jobs, task_to_job, job_result_roots
    require_client_auth(job.auth_token)

    job_submitted += 1
    job_id = f"job_{job_submitted}"

    tasks = job.payload.get("tasks")
    if tasks is not None:
        validate_tasks_payload(tasks)

    if tasks is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Jobs must include an explicit 'tasks' list. "
                "Built-in automatic decomposition is no longer provided by the Hive."
            ),
        )

    result_root = resolve_results_root(job.payload.get("results_subdir"))
    job_result_roots[job_id] = result_root

    jobs[job_id] = {
        "tasks_total": len(tasks),
        "tasks_completed": 0,
        "results_root": str(result_root),
    }

    for task in tasks:
        task.setdefault("requirements", {})

        task_to_job[task["task_id"]] = job_id
        state.add_task(task)

    return {
        "status": "job accepted",
        "job_id": job_id,
        "tasks_created": len(tasks),
    }


# --------------------------------------------------
# Get results
# --------------------------------------------------

@app.get("/results")
def get_results(job_id: Optional[str] = None):
    """Return all stored task results from the Hive."""

    if job_id is not None:
        return {
            task_id: result
            for task_id, result in state.results.items()
            if task_to_job.get(task_id) == job_id
        }
    return state.results


# --------------------------------------------------
# Hive status
# --------------------------------------------------

@app.get("/status")
def get_status():
    """
    Return a quick overview of the Hive state.
    Useful for monitoring BeeMesh while tasks are running.
    """

    workers_registered = len(state.workers)
    tasks_remaining = len(state.task_queue)
    tasks_completed = len(state.results)

    return {
        "workers_registered": workers_registered,
        "workers": state.workers,
        "tasks_remaining": tasks_remaining,
        "leased_tasks": len(state.leased_tasks),
        "tasks_completed": tasks_completed,
        "jobs_submitted": job_submitted,
        "jobs": jobs,
    }
