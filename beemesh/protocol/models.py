r"""
BeeMesh Protocol Models

These Pydantic models define the JSON messages exchanged between
the hive coordinator and worker bees.

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
    """Worker registration request"""

    hostname: str
    cpu_cores: int
    ram_gb: float
    gpu: Optional[str] = None
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
    """Message sent by the Hive to assign a task to a worker."""

    task_id: str
    task_type: str
    payload: Dict[str, Any]
    lease_timeout_s: Optional[int] = None


class TaskResponse(BaseModel):
    """Coordinator response when a worker requests a task."""

    task: Optional[Task] = None


# --------------------------------------------------
# Results
# --------------------------------------------------

class TaskResult(BaseModel):
    """Result submitted by a worker after completing a task."""

    worker_id: str
    task_id: str
    result: Dict[str, Any]
    auth_token: Optional[str] = None


# --------------------------------------------------
# Job Submission
# --------------------------------------------------

class JobSubmit(BaseModel):
    """Client request to submit a new job to the Hive."""

    job_type: str
    payload: Dict[str, Any]
    auth_token: Optional[str] = None
