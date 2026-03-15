# BeeMesh

**BeeMesh** is a lightweight volunteer distributed computing framework designed for scientific workloads. It allows a central **Hive coordinator** to distribute work across multiple **Bee workers** running on heterogeneous machines such as laptops, desktops, or clusters.

The goal of BeeMesh is to make it easy to execute distributed scientific simulations without complex cluster infrastructure.

---

# Core Idea

A central **Hive** manages a queue of tasks. Worker nodes called **Bees** connect to the Hive, request work, execute tasks, and return results.

```
                +------------------+
                |     BeeMesh      |
                |       Hive       |
                |   Task Queue     |
                +------------------+
                    ↑            ↑
                request        request
                    |            |
                +-------+     +-------+
                | Bee1  |     | Bee2  |
                +-------+     +-------+
                    |             |
                execute        execute
                    |             |
                result         result
            └──────submit_result──────┘
```

Whichever worker asks first receives the next available task.

---

# Architecture

BeeMesh consists of three main components:

### Hive (Coordinator)

The Hive is a FastAPI server responsible for:

- worker registration
- job submission
- task queue management
- result collection
- cluster monitoring

### Bees (Workers)

Workers connect to the Hive and continuously request tasks using **long polling**.

```
                +------------------+
                |      BeeMesh     |
                |       Hive       |
                |    Task Queue    |
                +------------------+
                   ▲            ▲
                   │            │
              long poll    long poll
                   │            │
              +--------+   +--------+
              | Bee 1  |   | Bee 2  |
              +--------+   +--------+
                   │            │
                execute      execute
                   │            │
                   └──submit_result──► Hive
```

### Client

A client submits a high‑level job to the Hive. The Hive decomposes the job into smaller tasks that can be executed in parallel.

```
                Client
                  │
                  │ submit_job (global simulation)
                  ▼
          +---------------------+
          |      BeeMesh Hive   |
          |  job decomposition  |
          +---------------------+
                    │
                    │ create tasks
                    ▼
                 Task Queue
                    │
             ┌──────┴──────┐
             │             │
           Bee1           Bee2
             │             │
           compute       compute
             │             │
             └──submit_result──► Hive
```

---

# Features

- Lightweight distributed task execution
- Worker capability reporting (CPU, RAM)
- Automatic job decomposition
- Live cluster monitoring via CLI
- Progress bars for job execution
- Cluster throughput metrics

---

# Example CLI Usage

Start the Hive:

```
beemesh hive
```

Start workers:

```
beemesh bee --hostname worker1
beemesh bee --hostname worker2
```

Submit a distributed diffusion job:

```
beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4
```

Monitor the cluster:

```
beemesh monitor
```

---

# Multi-Machine Launch

BeeMesh can run across multiple machines as long as every worker can reach the
Hive. `127.0.0.1` only works when the Hive and worker are on the same machine.

Start the Hive on the coordinator machine:

```
export BEEMESH_WORKER_TOKEN="shared-worker-token"
export BEEMESH_CLIENT_TOKEN="shared-client-token"
beemesh hive --host 0.0.0.0 --port 8000
```

Same LAN:

```
beemesh bee --hostname worker-a --hive-url http://192.168.1.10:8000 --auth-token shared-worker-token
beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4 --hive-url http://192.168.1.10:8000 --auth-token shared-client-token
```

Different networks with a public IP or VPS:

```
beemesh bee --hostname worker-a --hive-url http://<public-ip>:8000 --auth-token shared-worker-token
beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4 --hive-url http://<public-ip>:8000 --auth-token shared-client-token
```

Different networks with Tailscale:

```
beemesh bee --hostname worker-a --hive-url http://100.x.y.z:8000 --auth-token shared-worker-token
beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4 --hive-url http://100.x.y.z:8000 --auth-token shared-client-token
```

BeeMesh uses worker heartbeats and leased tasks, so unfinished work can be
requeued when a remote worker disappears.

---

# Project Vision

BeeMesh aims to provide a simple framework for:

- distributed scientific simulations
- volunteer computing
- heterogeneous cluster execution

Future work includes support for **domain‑decomposed PDE solvers**, enabling distributed simulations across many machines.

---

# License

MIT License
