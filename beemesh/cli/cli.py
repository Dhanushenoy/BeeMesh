"""
BeeMesh CLI

Command line interface for BeeMesh.

Examples:

    beemesh hive
    beemesh bee --hostname laptop
    beemesh submit-diffusion --nx 512 --ny 512 --blocks-x 4 --blocks-y 4
    beemesh status
"""

import argparse
import os
import sys
import requests

from beemesh.version import __version__

DEFAULT_AUTH_TOKEN = os.getenv("BEEMESH_AUTH_TOKEN", "")


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
    hive_url="http://127.0.0.1:8000",
    auth_token=DEFAULT_AUTH_TOKEN,
    heartbeat_interval=10.0,
):
    """Start a Bee worker."""
    from beemesh.worker.worker import BeeWorker

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


def show_status(hive_url):
    """Query Hive status."""

    try:
        r = requests.get(f"{hive_url}/status")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Hive. Is it running?")
        return

    print("\nHive status:")
    print(r.json())


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
                print("Error: Could not connect to Hive. Is it running?")
                break

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
                cpu = info.get("cpu_cores")
                ram = info.get("ram_gb")
                gpu = info.get("gpu")

                print(f"{wid:10} CPU={cpu} RAM={ram}GB GPU={gpu}")

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
    bee_cmd.add_argument("--hive-url", default="http://127.0.0.1:8000")
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
    submit_cmd.add_argument("--hive-url", default="http://127.0.0.1:8000")
    submit_cmd.add_argument("--auth-token", default=DEFAULT_AUTH_TOKEN)

    # Status command
    status_cmd = sub.add_parser("status", help="Show Hive status")
    status_cmd.add_argument("--hive-url", default="http://127.0.0.1:8000")

    # Monitor command
    monitor_cmd = sub.add_parser("monitor", help="Live Hive monitor")
    monitor_cmd.add_argument("--hive-url", default="http://127.0.0.1:8000")
    monitor_cmd.add_argument("--interval", type=int, default=2)

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


if __name__ == "__main__":
    main()
