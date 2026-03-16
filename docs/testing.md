# Testing

BeeMesh includes a small unit-level test suite covering the core coordinator,
launch, and worker execution paths.

## Install Test Dependencies

From the repository root:

```bash
pip install -e '.[test]'
```

This installs `pytest` and the FastAPI test client dependency used by the API
tests.

## Run the Full Test Suite

```bash
python -m pytest tests/
```

## Run Individual Test Modules

```bash
python -m pytest tests/test_scheduler.py
python -m pytest tests/test_state.py
python -m pytest tests/test_server.py
python -m pytest tests/test_launch.py
python -m pytest tests/test_executor.py
```

## What the Tests Cover

- `tests/test_scheduler.py`
  - worker eligibility checks
  - target-worker routing
  - scarcity-aware task selection
  - age-based task priority

- `tests/test_state.py`
  - duplicate task protection
  - task leasing and lease release
  - result ownership validation
  - expired-task requeue
  - dead-worker requeue behavior

- `tests/test_server.py`
  - worker and client auth enforcement
  - malformed task rejection
  - wrong-worker result rejection
  - job-scoped result filtering

- `tests/test_launch.py`
  - `parallel()` / `swarm()` script parsing
  - launch-time requirements hook behavior
  - unschedulable workload preflight checks
  - weighted strip partitioning for grid workloads

- `tests/test_executor.py`
  - unknown task type rejection
  - Python batch execution and failure capture
  - PDE tile kernel output shape and metadata
  - executable batch execution for uploaded binaries/scripts

## Scope

These tests are intentionally focused on core invariants and worker/coordinator
behavior. They do not currently provide full end-to-end multi-machine coverage.
Remote networking workflows such as VPN-based execution are still tested
manually.
