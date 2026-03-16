"""
BeeMesh CLI

Command line interface for BeeMesh.

Examples:

    beemesh hive
    beemesh bee --hostname laptop
    beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4
    beemesh status
    beemesh --launch code.py
"""

import argparse
import os
import sys

from beemesh.version import __version__

DEFAULT_AUTH_TOKEN = os.getenv("BEEMESH_AUTH_TOKEN", "")
DEFAULT_HIVE_URL = os.getenv("BEEMESH_HIVE_URL", "http://127.0.0.1:8000")


def supports_unicode_output() -> bool:
    """Return True when the current output stream can likely render Unicode cleanly."""
    override = os.getenv("BEEMESH_UNICODE")
    if override is not None:
        return override.lower() in {"1", "true", "yes", "on"}

    if not sys.stdout.isatty():
        return False

    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def banner():
    print(
        r"""
   ____               __  ___           __
  / __ )___  ___     /  |/  /___  _____/ /_
 / __  / _ \/ _ \   / /|_/ / __ \/ ___/ __ \
/ /_/ /  __/  __/  / /  / /  _/ (__  ) / / /
\____/\___/\___/  /_/  /_/\____/____/_/ /_/

BeeMesh - Distributed Volunteer Computing Framework
"""
    )


def run_hive(host="127.0.0.1", port=8000):
    """Start the BeeMesh Hive (FastAPI server)."""
    import uvicorn

    banner()
    print(f"Starting Hive at http://{host}:{port}")
    uvicorn.run("beemesh.coordinator.server:app", host=host, port=port, reload=False)


def run_bee(
    hostname="bee",
    hive_url=DEFAULT_HIVE_URL,
    auth_token=DEFAULT_AUTH_TOKEN,
    heartbeat_interval=10.0,
):
    """Start a Bee worker."""
    from beemesh.worker.worker import BeeWorker
    import requests

    banner()
    print(f"Starting Bee worker: {hostname}")
    print(f"Connecting to Hive at {hive_url}")
    worker = BeeWorker(
        hostname=hostname,
        hive_url=hive_url,
        auth_token=auth_token,
        heartbeat_interval=heartbeat_interval,
    )

    try:
        worker.run()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Hive. Is it running?")


def submit_diffusion(
    nx,
    ny,
    blocks_x,
    blocks_y,
    steps,
    alpha,
    hive_url,
    auth_token=DEFAULT_AUTH_TOKEN,
):
    """Submit a diffusion job to the Hive."""
    import requests

    payload = {
        "job_type": "diffusion",
        "payload": {
            "nx": nx,
            "ny": ny,
            "blocks_x": blocks_x,
            "blocks_y": blocks_y,
            "steps": steps,
            "alpha": alpha,
        },
        "auth_token": auth_token,
    }

    r = requests.post(f"{hive_url}/submit_job", json=payload)

    print("\nJob submission response:")
    print(r.json())


def launch_python_script(
    script_path,
    hive_url=DEFAULT_HIVE_URL,
    auth_token=DEFAULT_AUTH_TOKEN,
    wait_interval=2.0,
    live=False,
):
    """Launch a Python script using the BeeMesh parallel loop runner."""
    from beemesh.launch import launch_script

    banner()
    print(f"Launching {script_path} via BeeMesh")
    print(f"Hive URL: {hive_url}")
    launch_script(script_path, hive_url, auth_token, wait_interval, live)


def launch_executable_sweep(
    executable_path,
    sweep,
    hive_url=DEFAULT_HIVE_URL,
    auth_token=DEFAULT_AUTH_TOKEN,
    wait_interval=2.0,
):
    """Launch a native executable over a scalar sweep."""
    from beemesh.executable_launch import launch_executable

    banner()
    print(f"Launching executable {executable_path} via BeeMesh")
    print(f"Sweep: {sweep}")
    print(f"Hive URL: {hive_url}")
    launch_executable(executable_path, sweep, hive_url, auth_token, wait_interval)


def show_status(hive_url):
    """Query Hive status."""
    import requests

    try:
        r = requests.get(f"{hive_url}/status")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Hive. Is it running?")
        return

    data = r.json()
    workers = data.get("workers", {})
    jobs = data.get("jobs", {})

    print("\nBeeMesh Hive Status")
    print("=" * 40)
    print(f"Hive URL           : {hive_url}")
    print(f"Workers registered : {data.get('workers_registered', 0)}")
    print(f"Tasks remaining    : {data.get('tasks_remaining', 0)}")
    print(f"Leased tasks       : {data.get('leased_tasks', 0)}")
    print(f"Tasks completed    : {data.get('tasks_completed', 0)}")
    print(f"Jobs submitted     : {data.get('jobs_submitted', 0)}")

    print("\nWorkers")
    print("-" * 40)
    if not workers:
        print("No workers registered.")
    else:
        for worker_id, info in workers.items():
            hostname = info.get("hostname") or "-"
            status = info.get("status", "unknown")
            cpu = info.get("cpu_cores", "?")
            ram = info.get("ram_gb", "?")
            gpu = info.get("gpu") or "-"
            gpu_mem = info.get("gpu_memory_gb", 0.0)
            arch = info.get("architecture") or "-"
            perf = info.get("performance_score", "?")
            print(
                f"{hostname:18} ({worker_id}) {status:5} "
                f"CPU={cpu:<2} RAM={ram}GB GPU={gpu} "
                f"GPU_MEM={gpu_mem}GB ARCH={arch} SCORE={perf}"
            )

    print("\nJobs")
    print("-" * 40)
    if not jobs:
        print("No jobs submitted.")
    else:
        for job_id, info in jobs.items():
            total = info.get("tasks_total", 0)
            done = info.get("tasks_completed", 0)
            bar = progress_bar(done, total)
            results_root = info.get("results_root", "-")
            print(f"{job_id:10} {bar} ({done}/{total})")
            print(f"results_root: {results_root}")


# Progress bar helper for jobs
def progress_bar(done, total, width=20):
    """Render a simple ASCII progress bar."""
    if not total:
        return "[no tasks]"

    ratio = done / total
    filled = int(width * ratio)

    if supports_unicode_output():
        full, empty = "█", "░"
    else:
        full, empty = "#", "-"

    bar = full * filled + empty * (width - filled)
    percent = int(ratio * 100)

    return f"{bar} {percent}%"


def monitor_hive(hive_url, interval=2):
    """Continuously monitor Hive status."""
    import requests

    # Initial check to see if Hive is reachable
    try:
        r = requests.get(f"{hive_url}/status")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Hive. Is it running?")
        return

    import time

    print("\nBeeMesh live monitor (Ctrl+C to stop)\n")

    last_completed = 0
    last_time = time.time()

    try:
        while True:
            try:
                r = requests.get(f"{hive_url}/status")
            except requests.exceptions.ConnectionError:
                print(
                    "Error: Could not connect to Hive. Retrying in {} seconds...".format(
                        interval
                    )
                )
                time.sleep(interval)
                continue

            data = r.json()

            workers = data.get("workers", {})

            print("\033c", end="")  # clear screen
            print("BeeMesh Hive Monitor")
            print("=" * 40)

            workers_registered = data.get("workers_registered")
            tasks_remaining = data.get("tasks_remaining")
            tasks_completed = data.get("tasks_completed")
            jobs_submitted = data.get("jobs_submitted")

            # compute throughput
            now = time.time()
            dt = now - last_time
            throughput = 0
            if dt > 0:
                throughput = (tasks_completed - last_completed) / dt

            last_completed = tasks_completed
            last_time = now

            print(f"Workers registered : {workers_registered}")
            print(f"Tasks remaining    : {tasks_remaining}")
            print(f"Tasks completed    : {tasks_completed}")
            print(f"Jobs submitted     : {jobs_submitted}")
            print(f"Cluster throughput : {throughput:.2f} tasks/sec\n")

            print("Workers:")
            print("-" * 40)

            for wid, info in workers.items():
                hostname = info.get("hostname") or "-"
                status = info.get("status", "unknown")
                cpu = info.get("cpu_cores")
                ram = info.get("ram_gb")
                gpu = info.get("gpu") or "-"
                gpu_mem = info.get("gpu_memory_gb", 0.0)
                arch = info.get("architecture") or "-"

                print(
                    f"{hostname:18} ({wid}) {status:5} "
                    f"CPU={cpu} RAM={ram}GB GPU={gpu} GPU_MEM={gpu_mem}GB ARCH={arch}"
                )

            print("\nJobs:")
            print("-" * 40)

            jobs = data.get("jobs", {})

            for job_id, info in jobs.items():
                total = info.get("tasks_total", 0)
                done = info.get("tasks_completed", 0)

                bar = progress_bar(done, total)

                print(f"{job_id:10} {bar} ({done}/{total})")

            print("\n(refreshing every {}s)".format(interval))

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nMonitor stopped.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--launch":
        launch_parser = argparse.ArgumentParser(
            description="Launch a Python script through BeeMesh."
        )
        launch_parser.add_argument("--launch", dest="script_path", required=True)
        launch_parser.add_argument("--hive-url", default=DEFAULT_HIVE_URL)
        launch_parser.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)
        launch_parser.add_argument("--wait-interval", type=float, default=2.0)
        launch_parser.add_argument("--live", action="store_true")
        launch_args = launch_parser.parse_args()
        launch_python_script(
            launch_args.script_path,
            launch_args.hive_url,
            launch_args.auth_token,
            launch_args.wait_interval,
            launch_args.live,
        )
        return

    parser = argparse.ArgumentParser(
        description="BeeMesh CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"BeeMesh {__version__}")

    sub = parser.add_subparsers(dest="command")

    # Hive command
    hive_cmd = sub.add_parser("hive", help="Start the BeeMesh Hive server")
    hive_cmd.add_argument("--host", default="127.0.0.1")
    hive_cmd.add_argument("--port", type=int, default=8000)

    # Bee command
    bee_cmd = sub.add_parser("bee", help="Start a Bee worker")
    bee_cmd.add_argument("--hostname", default="bee")
    bee_cmd.add_argument("--hive-url", default=DEFAULT_HIVE_URL)
    bee_cmd.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)
    bee_cmd.add_argument("--heartbeat-interval", type=float, default=10.0)

    # Submit diffusion job
    submit_cmd = sub.add_parser("submit-diffusion", help="Submit a diffusion job")
    submit_cmd.add_argument("--nx", type=int, default=256)
    submit_cmd.add_argument("--ny", type=int, default=256)
    submit_cmd.add_argument("--blocks-x", type=int, default=4)
    submit_cmd.add_argument("--blocks-y", type=int, default=4)
    submit_cmd.add_argument("--steps", type=int, default=2000)
    submit_cmd.add_argument("--alpha", type=float, default=0.1)
    submit_cmd.add_argument("--hive-url", default=DEFAULT_HIVE_URL)
    submit_cmd.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)

    # Status command
    status_cmd = sub.add_parser("status", help="Show Hive status")
    status_cmd.add_argument("--hive-url", default=DEFAULT_HIVE_URL)

    # Monitor command
    monitor_cmd = sub.add_parser("monitor", help="Live Hive monitor")
    monitor_cmd.add_argument("--hive-url", default=DEFAULT_HIVE_URL)
    monitor_cmd.add_argument("--interval", type=int, default=2)

    # Executable sweep command
    launch_cmd = sub.add_parser("launch", help="Launch a native executable sweep")
    launch_cmd.add_argument("executable_path")
    launch_cmd.add_argument("--sweep", required=True, help="start:end or start:end:step")
    launch_cmd.add_argument("--hive-url", default=DEFAULT_HIVE_URL)
    launch_cmd.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)
    launch_cmd.add_argument("--wait-interval", type=float, default=2.0)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "hive":
        run_hive(args.host, args.port)

    elif args.command == "bee":
        run_bee(
            args.hostname,
            args.hive_url,
            args.auth_token,
            args.heartbeat_interval,
        )

    elif args.command == "submit-diffusion":
        submit_diffusion(
            args.nx,
            args.ny,
            args.blocks_x,
            args.blocks_y,
            args.steps,
            args.alpha,
            args.hive_url,
            args.auth_token,
        )

    elif args.command == "status":
        show_status(args.hive_url)

    elif args.command == "monitor":
        monitor_hive(args.hive_url, args.interval)

    elif args.command == "launch":
        launch_executable_sweep(
            args.executable_path,
            args.sweep,
            args.hive_url,
            args.auth_token,
            args.wait_interval,
        )


if __name__ == "__main__":
    main()
