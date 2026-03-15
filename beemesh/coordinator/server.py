r"""
BeeMesh Hive Server

FastAPI server acting as the BeeMesh coordinator (Hive).
Workers (Bees) register with the Hive, request tasks, and submit results.

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

# simple job tracking in memory for v0
job_submitted = 0

# Job tracking structures
jobs: Dict[str, Dict[str, Any]] = {}
task_to_job: Dict[str, str] = {}


def require_worker_auth(token: Optional[str]) -> None:
    """Validate worker-facing requests when auth is enabled."""

    if WORKER_AUTH_TOKEN and token != WORKER_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid worker auth token")


def require_client_auth(token: Optional[str]) -> None:
    """Validate client job submission when auth is enabled."""

    if CLIENT_AUTH_TOKEN and token != CLIENT_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid client auth token")

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
    state.store_result(res.worker_id, res.task_id, res.result)

    job_id = task_to_job.get(res.task_id)

    if job_id and job_id in jobs:
        jobs[job_id]["tasks_completed"] += 1

    return {"status": "results stored"}


# --------------------------------------------------
# Submit a new job
# --------------------------------------------------

@app.post("/submit_job")
def submit_job(job: JobSubmit):
    """Submit a new job to the hive."""

    global job_submitted, jobs, task_to_job
    require_client_auth(job.auth_token)

    job_submitted += 1
    job_id = f"job_{job_submitted}"

    tasks = job.payload.get("tasks")

    # Automatic job decomposition
    if tasks is None:

        job_type = job.job_type
        payload = job.payload

        if job_type == "diffusion":

            nx = payload.get("nx")
            ny = payload.get("ny")
            if nx is None or ny is None:
                raise HTTPException(
                    status_code=400,
                    detail="Diffusion jobs require 'nx' and 'ny' in the payload.",
                )

            blocks_x = payload.get("blocks_x", 1)
            blocks_y = payload.get("blocks_y", 1)
            if blocks_x <= 0 or blocks_y <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="'blocks_x' and 'blocks_y' must be positive integers.",
                )
            if nx <= 0 or ny <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="'nx' and 'ny' must be positive integers.",
                )
            if nx < blocks_x or ny < blocks_y:
                raise HTTPException(
                    status_code=400,
                    detail="Grid dimensions must be at least as large as the block counts.",
                )

            steps = payload.get("steps", 100)
            alpha = payload.get("alpha", 0.1)

            tasks = []
            task_id_counter = 0

            bx_size = nx // blocks_x
            by_size = ny // blocks_y

            for bx in range(blocks_x):
                for by in range(blocks_y):

                    task = {
                        "task_id": f"{job_id}_task_{task_id_counter}",
                        "task_type": "diffusion",
                        "payload": {
                            "nx": bx_size,
                            "ny": by_size,
                            "steps": steps,
                            "alpha": alpha,
                            "block_x": bx,
                            "block_y": by,
                            "blocks_x": blocks_x,
                            "blocks_y": blocks_y,
                        },
                    }

                    tasks.append(task)
                    task_id_counter += 1

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported job type: {job_type}",
            )

    jobs[job_id] = {
        "tasks_total": len(tasks),
        "tasks_completed": 0,
    }

    for task in tasks:

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
def get_results():
    """Return all stored task results from the Hive."""

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
