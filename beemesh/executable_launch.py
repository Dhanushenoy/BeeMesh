"""
BeeMesh launch support for sweeping native executables.

This mode ships a local executable to compatible workers, runs it for a range
of scalar case values, and gathers stdout/stderr back through the Hive.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import platform
import re
import time
from typing import Any, Dict, List, Optional
import uuid

from beemesh.launch import preflight_worker_fit


CASE_PATTERN = re.compile(
    r"Case\s+(?P<case>-?\d+)\s+result\s+(?P<value>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
)
NUMERIC_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _build_batches(cases: List[Any], workers: Dict[str, Dict[str, object]]) -> List[List[Any]]:
    active_workers = [
        info for info in workers.values() if info.get("status", "alive") == "alive"
    ]
    if not active_workers:
        raise RuntimeError("No alive workers are registered with the Hive.")

    total_capacity = sum(max(int(info.get("cpu_cores", 1) or 1), 1) for info in active_workers)
    num_batches = min(len(cases), max(total_capacity, 1))
    batches = [[] for _ in range(num_batches)]
    for index, case in enumerate(cases):
        batches[index % num_batches].append(case)
    return [batch for batch in batches if batch]


def _print_monitor_hint(hive_url: str) -> None:
    command = f"beemesh monitor --hive-url {hive_url}"
    border = "=" * max(len(command), 24)
    print("\nMonitor Command")
    print(border)
    print(command)
    print(border)
    print("Press Ctrl+C to stop waiting here and run the monitor command.")


def _parse_sweep(spec: str) -> List[int]:
    parts = spec.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Sweep must be formatted as start:end or start:end:step")

    start = int(parts[0])
    end = int(parts[1])
    step = int(parts[2]) if len(parts) == 3 else 1
    if step == 0:
        raise ValueError("Sweep step cannot be zero")

    return list(range(start, end, step))


def _results_subdir_for_executable(executable: Path) -> str:
    """Return a repo-relative server_results path for an executable launch."""

    repo_root = Path(__file__).resolve().parent.parent
    try:
        return str(executable.parent.relative_to(repo_root) / "server_results")
    except ValueError:
        return ""


def _extract_points(task_results: Dict[str, Dict[str, object]]):
    points = []
    for task_id in sorted(task_results):
        result = task_results[task_id]
        for entry in result.get("outputs", []):
            stdout = entry.get("stdout", "")
            matched = False
            for line in stdout.splitlines():
                match = CASE_PATTERN.search(line.strip())
                if match:
                    points.append(
                        {
                            "case": int(match.group("case")),
                            "result": float(match.group("value")),
                        }
                    )
                    matched = True
            if matched:
                continue

            numeric_match = NUMERIC_PATTERN.search(stdout.strip())
            if numeric_match:
                points.append(
                    {
                        "case": int(entry.get("case")),
                        "result": float(numeric_match.group(0)),
                    }
                )
    return sorted(points, key=lambda item: item["case"])


def launch_executable(
    executable_path: str,
    sweep: Optional[str],
    hive_url: str,
    auth_token: str,
    wait_interval: float = 2.0,
) -> None:
    import requests

    executable = Path(executable_path).resolve()
    if not executable.exists():
        raise FileNotFoundError(f"Executable not found: {executable}")
    if not executable.is_file():
        raise ValueError(f"Expected a file path for executable: {executable}")

    cases = _parse_sweep(sweep) if sweep is not None else [None]
    if not cases:
        print("Sweep produced no cases. Nothing to launch.")
        return

    executable_blob = base64.b64encode(executable.read_bytes()).decode("ascii")
    status_response = requests.get(f"{hive_url}/status", timeout=30)
    status_response.raise_for_status()
    workers = status_response.json().get("workers", {})
    if not workers:
        raise RuntimeError("No workers are registered with the Hive.")

    active_workers = [
        worker_id
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    ]
    batches = _build_batches(cases, workers)
    launch_id = uuid.uuid4().hex[:8]

    results_subdir = _results_subdir_for_executable(executable)

    arch = platform.machine() or None
    tasks = []
    for index, batch in enumerate(batches):
        tasks.append(
            {
                "task_id": f"executable_batch_{launch_id}_{index}",
                "task_type": "executable_batch",
                "payload": {
                    "executable_name": executable.name,
                    "executable_blob_b64": executable_blob,
                    "cases": batch,
                },
                "requirements": {
                    "preferred_device": "cpu",
                    "min_cpu_cores": 1,
                    "min_ram_gb": 0.25,
                    "estimated_cost": max(1.0, round(len(batch) * 1.5, 2)),
                    "architecture": arch,
                },
            }
        )

    preflight_worker_fit(tasks, workers)

    submit_payload = {
        "job_type": "executable_batch",
        "payload": {
            "tasks": tasks,
            "results_subdir": results_subdir,
        },
        "auth_token": auth_token,
    }
    submit_response = requests.post(f"{hive_url}/submit_job", json=submit_payload, timeout=30)
    submit_response.raise_for_status()
    start_time = time.perf_counter()

    print("Launch response:")
    print(submit_response.json())
    print(f"Executable: {executable}")
    if sweep is None:
        print("Mode: single-run (no sweep)")
    else:
        print(f"Sweep: {sweep}")
    print(f"Dispatched across {len(active_workers)} bee(s).")
    _print_monitor_hint(hive_url)

    task_ids = {task["task_id"] for task in tasks}
    pending = set(task_ids)
    completed_results: Dict[str, Dict[str, object]] = {}
    print(f"Waiting for {len(task_ids)} executable batch tasks to finish...")

    try:
        while pending:
            results_response = requests.get(f"{hive_url}/results", timeout=30)
            results_response.raise_for_status()
            results = results_response.json()

            finished = pending.intersection(results)
            for task_id in sorted(finished):
                result = results[task_id]
                completed_results[task_id] = result
                print(f"\n[{task_id}] cases={result.get('cases_processed')}")
                if result.get("__beemesh_result_file__"):
                    print(f"saved={result['__beemesh_result_file__']}")
                for entry in result.get("outputs", []):
                    stdout = entry.get("stdout", "")
                    stderr = entry.get("stderr", "")
                    if stdout:
                        print(stdout, end="" if stdout.endswith("\n") else "\n")
                    if stderr:
                        print(stderr, end="" if stderr.endswith("\n") else "\n")
                pending.remove(task_id)

            if pending:
                time.sleep(wait_interval)
    except KeyboardInterrupt:
        print("\nLaunch detached. Remote tasks continue running on the Hive.")
        _print_monitor_hint(hive_url)
        return

    result_paths = [
        Path(result["__beemesh_result_file__"])
        for result in completed_results.values()
        if result.get("__beemesh_result_file__")
    ]
    results_dir = result_paths[0].parent if result_paths else None

    scenario_dir = executable.parent
    data_dir = scenario_dir / "data"
    data_dir.mkdir(exist_ok=True)
    raw_results_path = data_dir / "raw_task_results.json"
    parsed_results_path = data_dir / "executable_sweep.json"
    benchmark_path = data_dir / "benchmark_runs.json"
    raw_results_path.write_text(json.dumps(completed_results, indent=2), encoding="utf-8")

    points = _extract_points(completed_results)
    parsed_results_path.write_text(json.dumps(points, indent=2), encoding="utf-8")
    duration_s = round(time.perf_counter() - start_time, 3)
    benchmark_entry = {
        "executable": executable.name,
        "sweep": sweep,
        "bee_count": len(active_workers),
        "task_batches": len(task_ids),
        "duration_s": duration_s,
        "cases": len(cases),
    }
    if benchmark_path.exists():
        benchmark_runs = json.loads(benchmark_path.read_text(encoding="utf-8"))
    else:
        benchmark_runs = []
    benchmark_runs.append(benchmark_entry)
    benchmark_path.write_text(json.dumps(benchmark_runs, indent=2), encoding="utf-8")

    visualize_script = scenario_dir / "visualize.py"
    if results_dir is not None:
        print(f"Hive result files: {results_dir}")
    print(f"Saved raw task results to {raw_results_path}")
    print(f"Saved parsed data to {parsed_results_path}")
    print(f"Saved benchmark run to {benchmark_path}")
    print(f"Run summary: {len(active_workers)} bee(s), {duration_s}s total runtime")
    if visualize_script.exists():
        print(f"Visualize with: python {visualize_script}")
