r"""
BeeMesh Protocol Models

Pydantic schemas for the JSON messages exchanged between the Hive,
Bee workers, and job-submitting clients.

The protocol covers:
- worker registration, heartbeats, task requests, and result submission
- Hive-to-worker task assignment messages
- client job submission requests

Auth tokens are optional at the schema level because Hive auth is
runtime-configurable; a deployed Hive may still require them.

Protocol flow:

    [Bee] -- WorkerRegister --> [Hive]
    [Bee] <-- WorkerRegisterResponse -- [Hive]

    [Bee] -- TaskRequest --> [Hive]
    [Bee] <-- TaskResponse(Task) -- [Hive]

    [Bee] -- TaskResult --> [Hive]
    [Client] -- JobSubmit --> [Hive]

Honeycomb metaphor:

          __     __     __
         /  \___/  \___/  \
         \__/ T \__/ R \__/
         /  \___/  \___/  \
         \__/ W \__/ H \__/
            register  assign

  W = worker bee message
  T = task cell
  R = result cell
  H = hive coordinator
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


# --------------------------------------------------
# Worker Registration
# --------------------------------------------------

class WorkerRegister(BaseModel):
    """Worker registration request sent by a Bee to the Hive."""

    hostname: str
    cpu_cores: int
    ram_gb: float
    gpu: Optional[str] = None
    gpu_memory_gb: float = 0.0
    architecture: Optional[str] = None
    auth_token: Optional[str] = None


class WorkerRegisterResponse(BaseModel):
    """Response returned after a worker registration."""

    worker_id: str


# --------------------------------------------------
# Task Handling
# --------------------------------------------------

class TaskRequest(BaseModel):
    """Worker asking the coordinator for a task to execute."""

    worker_id: str
    auth_token: Optional[str] = None


class Heartbeat(BaseModel):
    """Periodic liveness update sent by a worker to the Hive."""

    worker_id: str
    auth_token: Optional[str] = None


class Task(BaseModel):
    """Task assignment sent by the Hive to a worker."""

    task_id: str
    task_type: str
    payload: Dict[str, Any]
    requirements: Optional[Dict[str, Any]] = None
    lease_timeout_s: Optional[int] = None


class TaskResponse(BaseModel):
    """Coordinator response when a worker requests a task."""

    task: Optional[Task] = None


# --------------------------------------------------
# Results
# --------------------------------------------------

class TaskResult(BaseModel):
    """Completed task result submitted by a worker."""

    worker_id: str
    task_id: str
    result: Dict[str, Any]
    auth_token: Optional[str] = None


# --------------------------------------------------
# Job Submission
# --------------------------------------------------

class JobSubmit(BaseModel):
    """Client request to submit a job to the Hive."""

    job_type: str
    payload: Dict[str, Any]
    auth_token: Optional[str] = None
