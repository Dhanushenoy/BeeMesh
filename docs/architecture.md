# Architecture

BeeMesh follows a simple coordinator-worker model:

- the **Hive** is the central coordinator
- **Bees** are worker processes that register with the Hive and execute tasks
- clients submit jobs to the Hive as explicit task batches

## Main Components

### Hive Coordinator

The Hive is implemented by three core modules:

- [beemesh/coordinator/server.py](/Users/dhanush/Codes/beemesh/beemesh/coordinator/server.py)
- [beemesh/coordinator/server.py](../beemesh/coordinator/server.py)
  - FastAPI API surface
  - worker registration, heartbeats, task requests, result submission
  - client job submission and result/status endpoints

- [beemesh/coordinator/state.py](../beemesh/coordinator/state.py)
  - in-memory runtime state
  - worker registry and liveness metadata
  - queued tasks, leased tasks, and completed results
  - lease timeout and requeue behavior

- [beemesh/coordinator/scheduler.py](../beemesh/coordinator/scheduler.py)
  - worker eligibility checks
  - worker-strength scoring
  - scarcity-aware task selection
  - bounded age-based anti-starvation priority

### Bee Worker

The worker side is implemented by:

- [beemesh/worker/worker.py](../beemesh/worker/worker.py)
  - capability detection
  - registration with the Hive
  - heartbeat loop
  - task polling, execution, and result submission

- [beemesh/worker/executor.py](../beemesh/worker/executor.py)
  - maps `task_type` values to built-in workload implementations

### Workloads

Built-in workload kernels live under:

- [beemesh/workloads/python_batch.py](../beemesh/workloads/python_batch.py)
  - distributed execution of shipped Python loop batches

- [beemesh/workloads/executable_batch.py](../beemesh/workloads/executable_batch.py)
  - execution of uploaded compiled executables over a case sweep

- [beemesh/workloads/pde_timestep_tile.py](../beemesh/workloads/pde_timestep_tile.py)
  - one ghosted-tile PDE timestep for the experimental grid workflow

## Execution Flow

### 1. Worker Registration

Each Bee sends a registration request containing:

- hostname
- CPU cores
- RAM
- GPU metadata
- architecture
- optional auth token

The Hive assigns a `worker_id` and stores worker metadata in `HiveState`.

### 2. Job Submission

Clients submit jobs through `/submit_job`.

BeeMesh currently expects jobs to arrive as explicit task lists. The Hive does
not perform general job decomposition internally. Launch-side tooling is
responsible for generating task batches.

### 3. Task Leasing

Workers repeatedly call `/request_task`.

The Hive:

- requeues expired leases
- sweeps dead workers based on heartbeat timeout
- selects the best task for the requesting worker
- records lease metadata and active-task counts

Leases are bounded in time so unfinished work can be reassigned if a worker
disappears.

### 4. Task Execution

The Bee executes the assigned task locally using the worker executor.

Results are sent back to `/submit_result`. Failed task execution is still
reported back as a structured result so the worker process can stay alive.

### 5. Result Persistence

The Hive stores completed task results:

- in memory for status and polling
- on disk under a job-specific result directory

Many example launch scripts also perform local post-processing and
visualization after remote work finishes.

## Scheduling Model

BeeMesh uses explicit heuristic scheduling rather than a black-box policy.

Hard filters:

- worker liveness
- minimum CPU cores
- minimum RAM
- GPU requirement
- minimum GPU memory
- architecture match
- optional `target_worker_id`

Soft scoring:

- worker CPU, RAM, and GPU capacity
- worker performance score
- current active load
- preferred device hints
- task estimated cost
- scarcity bonus for tasks that only a few bees can run
- bounded age bonus for older queued tasks

## Execution Models

### Python Batch Launch

`beemesh launch script.py`

The launcher parses one `with beemesh.parallel():` or `with beemesh.swarm():`
block, batches the iterable cases, and submits `python_batch` tasks.

### Executable Sweep Launch

`beemesh launch ./simulate_case --sweep 0:1000`

The launcher uploads the executable bytes and creates `executable_batch` tasks
over the requested case sweep.

### Experimental Grid Workflow

`with beemesh.parallel(grid=u):`

The current grid path is experimental and implemented for the included 2D
advection example. The launch side partitions the field, extracts ghosted
tiles, submits one PDE timestep task per tile, and reassembles the global field
between steps.

This is a synchronized Hive-mediated workflow, not yet a persistent
subdomain-resident PDE runtime.

## Current Architectural Limits

- Hive state is in memory only
- job bookkeeping is still partly owned by the API layer
- coupled PDE execution is experimental
- no persistent long-running PDE subdomain workers yet
- no direct bee-to-bee halo exchange
- security is intended for controlled environments rather than hardened public deployment
