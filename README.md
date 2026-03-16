# BeeMesh
![PyPI](https://img.shields.io/pypi/v/bee-mesh)
![Python](https://img.shields.io/pypi/pyversions/bee-mesh)
![License](https://img.shields.io/github/license/Dhanushenoy/BeeMesh)
![Tests](https://img.shields.io/github/actions/workflow/status/Dhanushenoy/BeeMesh/tests.yml?label=tests)

*A lightweight distributed computing framework for scientific workloads across heterogeneous machines.*

BeeMesh enables Python scripts and external executables (e.g., C, C++, or Fortran programs) to run across multiple machines with minimal setup.

A central **Hive coordinator** distributes tasks to connected **Bee workers**, allowing researchers to execute simulations, parameter sweeps, and numerical experiments across laptops, desktops, clusters, or remote machines.

---

## Core Idea

BeeMesh follows a simple **Hive–Bee** architecture:

```text
           +------------------+
           |       Hive       |
           |   Task Queue     |
           +------------------+
              ↑            ↑
           request      request
              |            |
          +-------+    +-------+
          | Bee 1 |    | Bee 2 |
          +-------+    +-------+
              |            |
           execute      execute
              |            |
           result       result
              └──submit_result──► Hive
```

The Hive acts as the central coordinator and scheduler. Each Bee periodically requests available work, executes its assigned task, and returns the results to the Hive.

This model allows BeeMesh to run across a single machine, a local network, or multiple remote machines connected through VPN or public networking.

## Installation
BeeMesh requires Python 3.9 or newer.

Install from PyPI:

```bash
pip install bee-mesh
```

Or install from source:

```bash
git clone https://github.com/Dhanushenoy/BeeMesh.git
cd BeeMesh

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

It is recommended to use a virtual environment.

Verify the installation:

```bash
beemesh --help
```

## Testing

Install the test dependencies:

```bash
pip install -e '.[test]'
```

If installing from PyPI instead of source:

```bash
pip install 'bee-mesh[test]'
```

Run the test suite:

```bash
python -m pytest tests/
```

Detailed test coverage notes are available in [docs/testing.md](docs/testing.md).

## Quick Start

### Local Single-Machine Run

The explicit flags below are optional and shown for clarity. By default, the Hive starts on `127.0.0.1:8000`, and a Bee connects to that local address automatically. Authentication is mainly needed for remote or multi-machine deployments; the local quick-start below uses the default local setup.

Start the Hive:

```bash
beemesh hive
```

Equivalent explicit form:

```bash
beemesh hive --host 127.0.0.1 --port 8000
```

Start a Bee worker in another terminal:

```bash
beemesh bee
```

Equivalent explicit form:

```bash
beemesh bee --hostname local-bee --hive-url http://127.0.0.1:8000
```

BeeMesh can automatically distribute independent loop iterations across connected workers:

```python
import beemesh

cases = range(100)

with beemesh.parallel():
    for case in cases:
        print(case)
```

BeeMesh will detect the parallel loop, split the workload, and dispatch batches across available Bee workers.

```bash
beemesh launch examples/parallel_sweep_test/launch.py --hive-url http://127.0.0.1:8000
```

### Multi-Machine Run over VPN

BeeMesh can also run across multiple machines as long as all workers can reach the Hive.

**Example: Remote Execution over VPN**

In testing, BeeMesh was successfully run over Tailscale between two machines located in different countries.

On the Hive machine:

```bash
export BEEMESH_WORKER_TOKEN="shared-worker-token"
export BEEMESH_CLIENT_TOKEN="shared-client-token"
beemesh hive --host 0.0.0.0 --port 8000
```

On a remote Bee machine connected through Tailscale:

```bash
export BEEMESH_AUTH_TOKEN="shared-worker-token"
beemesh bee --hostname remote-bee --hive-url http://100.x.y.z:8000
```

Launch a job from the Hive machine or any authorized client:

```bash
beemesh launch examples/parallel_sweep_test/launch.py --hive-url http://100.x.y.z:8000 --auth-token shared-client-token
```

Replace `100.x.y.z` with the Tailscale IP address of the Hive machine.

### Monitoring

To monitor the Hive while jobs are running:

```bash
beemesh monitor --hive-url http://127.0.0.1:8000
```

For remote runs, replace the Hive URL with the Tailscale address.

## Core Features

BeeMesh supports several distributed workload patterns:

- **Python loop distribution** via `beemesh.parallel()` or `beemesh.swarm()`, allowing independent cases in a Python script to be automatically dispatched across connected Bee workers.

- **Executable sweeps** for compiled binaries (e.g., C, C++, or Fortran programs), enabling existing simulation codes to run across multiple machines without modification.

- **Capability-aware scheduling** using worker metadata such as CPU cores, RAM, GPU availability, and architecture.

- **Heterogeneous multi-machine execution**, allowing workloads to run across laptops, desktops, and remote machines connected through LAN, VPN, or the public internet.

- **Experimental coupled-grid PDE execution**, demonstrated by a 2D advection example using tiled domain decomposition with ghost-cell exchange between subdomains.

- **Lightweight deployment**, requiring only a central Hive coordinator and Bee workers, without dedicated cluster infrastructure.

## Execution Models

BeeMesh currently supports three main execution styles:

- **Python launch mode** via `beemesh launch script.py`, where BeeMesh parses a Python script containing `with beemesh.parallel():` or `with beemesh.swarm():` and distributes independent loop iterations across workers.
- **Executable launch mode** via `beemesh launch <executable> --sweep ...`, where a compiled binary is distributed and executed across workers for a parameter sweep.
- **Experimental grid mode** via `with beemesh.parallel(grid=u):`, where a structured 2D field is partitioned into tiles and advanced using a coupled ghost-exchange workflow.

In general:

- Use `parallel()` / `swarm()` for embarrassingly parallel Python workloads.
- Use `launch <executable>` for existing compiled simulation codes.
- Use the grid mode only for the current experimental PDE demonstrations.

## Current Limitations

BeeMesh is still an early-stage research software prototype. Important current limitations include:

- The coupled-grid PDE support is experimental and currently implemented only for the included 2D advection example.
- GPU-aware scheduling depends on worker GPU detection, which is still minimal.
- The Hive stores state in memory, so a restart will lose active job state.
- Some job bookkeeping still lives in the API layer; moving job metadata into a dedicated Hive state/store layer remains a future refactor.
- The distributed PDE path currently uses Hive-mediated synchronization rather than persistent long-running subdomain workers.
- Security and authentication are lightweight and intended for controlled environments, not hardened public deployment.
- The executable launch path assumes workers are compatible with the uploaded binary's operating system and architecture.

## Example Workloads

The repository includes several runnable examples:
- Parallel sweep test — simple distributed Python loop execution
- Monte Carlo test — distributed Monte Carlo / parameter sweep workflow
- Neural network hyperparameter search — distributed training runs across workers
- Mandelbrot test — tiled fractal rendering distributed across Bees
- 2D advection grid test — experimental structured-grid PDE execution with ghost-cell exchange
- C++ executable test — distributed sweep of a compiled executable across multiple workers

```text
examples/parallel_sweep_test
examples/monte_carlo_test
examples/nn_hyperparam_test
examples/mandelbrot_test
examples/advection_grid_test
examples/cpp_exec_test
```

Example commands:

```bash
beemesh launch examples/parallel_sweep_test/launch.py
beemesh launch examples/monte_carlo_test/launch.py
beemesh launch examples/nn_hyperparam_test/launch.py
beemesh launch examples/mandelbrot_test/launch.py --live
beemesh launch examples/advection_grid_test/launch.py
beemesh launch ./examples/cpp_exec_test/simulate_case --sweep 0:1000
```

## Executing External Programs

BeeMesh can also distribute compiled executables across workers.

For example, after building a C++ program such as simulate_case, BeeMesh can distribute a parameter sweep across multiple machines:

```bash
beemesh launch ./examples/cpp_exec_test/simulate_case --sweep 0:1000
```

This allows existing scientific programs written in C, C++, or Fortran to run on BeeMesh without rewriting them in Python.

## Fault Tolerance and Result Handling

BeeMesh uses worker heartbeats and leased tasks, so unfinished work can be requeued when a worker disconnects or becomes unavailable.

Completed task results are stored on the Hive under:

```text
server_results/<job_id>/
```

The results directory can be changed using:

```text
BEEMESH_RESULTS_DIR
```

Many included examples also define `beemesh_finalize(...)` hooks for automatic result collection, plotting, and post-processing after remote execution completes.

## Project Vision

BeeMesh aims to provide a simple framework for:

- distributed scientific simulations
- volunteer computing
- heterogeneous cluster execution
- lightweight multi-machine experimentation

Future development directions include:

- more advanced domain-decomposed PDE solvers
- improved GPU-aware scheduling
- larger-scale volunteer computing deployments
- richer distributed numerical workloads

## Related Projects

BeeMesh shares goals with other distributed computing frameworks:

- **Ray** – distributed Python execution
- **Dask** – parallel computing for Python
- **BOINC** – large-scale volunteer computing

BeeMesh focuses on lightweight deployment and simple distribution of scientific workloads across heterogeneous machines.

## License

BeeMesh is released under the MIT License.
