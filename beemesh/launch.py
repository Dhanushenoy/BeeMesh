"""
BeeMesh launch support for Python scripts using ``with beemesh.parallel():``.

Current MVP constraints:
- exactly one ``with beemesh.parallel():`` block
- the block must contain exactly one ``for`` loop
- work is split into remote batches based on aggregate worker CPU capacity
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import inspect
from pathlib import Path
import textwrap
from typing import Any, Dict, List, Optional
import uuid

from beemesh.coordinator.scheduler import worker_can_run_task


@dataclass
class ParallelSpec:
    """Extracted information for a single parallel loop."""

    prelude_source: str
    iterable_expr: str
    loop_target: str
    loop_body: str
    parallel_kwargs: Dict[str, str]


@dataclass
class LaunchContext:
    """Locally evaluated launch-time context for a script."""

    cases: List[Any]
    namespace: Dict[str, Any]
    captured_inputs: List[Dict[str, str]]


def _is_beemesh_parallel(expr: ast.AST) -> bool:
    """Return True for BeeMesh distributed-loop context expressions."""

    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr in {"parallel", "swarm"}
        and isinstance(expr.func.value, ast.Name)
        and expr.func.value.id == "beemesh"
    )


def _parallel_call(expr: ast.AST) -> Optional[ast.Call]:
    """Return the underlying BeeMesh launch call if present."""

    if _is_beemesh_parallel(expr):
        return expr
    return None


def extract_parallel_spec(script_path: str) -> ParallelSpec:
    """Parse a script and extract the first BeeMesh parallel loop."""

    source = Path(script_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script_path)
    parallel_blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With)
        and any(_is_beemesh_parallel(item.context_expr) for item in node.items)
    ]

    if not parallel_blocks:
        raise ValueError("No 'with beemesh.parallel():' block found in the script.")
    if len(parallel_blocks) > 1:
        raise ValueError("BeeMesh MVP supports exactly one parallel block per script.")

    with_node = parallel_blocks[0]
    parallel_call = None
    for item in with_node.items:
        parallel_call = _parallel_call(item.context_expr)
        if parallel_call is not None:
            break

    if len(with_node.body) != 1 or not isinstance(with_node.body[0], ast.For):
        raise ValueError(
            "BeeMesh MVP expects the parallel block to contain exactly one for-loop."
        )

    for_node = with_node.body[0]
    loop_target = ast.get_source_segment(source, for_node.target)
    iterable_expr = ast.get_source_segment(source, for_node.iter)
    if loop_target is None or iterable_expr is None:
        raise ValueError("Could not extract loop target or iterable from the script.")

    body_segments = [ast.get_source_segment(source, stmt) for stmt in for_node.body]
    loop_body = textwrap.dedent(
        "\n".join(segment for segment in body_segments if segment is not None)
    ).strip()

    lines = source.splitlines()
    prelude_source = "\n".join(lines[: with_node.lineno - 1]).rstrip()
    if prelude_source:
        prelude_source += "\n"

    parallel_kwargs: Dict[str, str] = {}
    if parallel_call is not None:
        for keyword in parallel_call.keywords:
            if keyword.arg is None:
                continue
            value_source = ast.get_source_segment(source, keyword.value)
            if value_source is not None:
                parallel_kwargs[keyword.arg] = value_source

    return ParallelSpec(
        prelude_source=prelude_source,
        iterable_expr=iterable_expr,
        loop_target=loop_target,
        loop_body=loop_body,
        parallel_kwargs=parallel_kwargs,
    )


def _load_cases(script_path: str, spec: ParallelSpec) -> LaunchContext:
    """Execute the script prelude locally and evaluate the loop iterable."""

    captured_inputs: List[Dict[str, str]] = []

    def record_input(prompt: str = "") -> str:
        response = builtins.input(prompt)
        captured_inputs.append({"prompt": str(prompt), "response": response})
        return response

    namespace: Dict[str, Any] = {
        "__file__": script_path,
        "__name__": "__beemesh_launch__",
        "input": record_input,
    }
    if spec.prelude_source.strip():
        exec(compile(spec.prelude_source, script_path, "exec"), namespace, namespace)
    cases = eval(spec.iterable_expr, namespace, namespace)
    return LaunchContext(
        cases=list(cases),
        namespace=namespace,
        captured_inputs=captured_inputs,
    )


def _build_batches(cases: List[Any], workers: Dict[str, Dict[str, Any]]) -> List[List[Any]]:
    """Split cases into batches based on total reported worker CPU capacity."""

    active_workers = [
        info for info in workers.values() if info.get("status", "alive") == "alive"
    ]
    if not active_workers:
        raise RuntimeError("No alive workers are registered with the Hive.")
    total_capacity = sum(max(int(info.get("cpu_cores", 1)), 1) for info in active_workers)
    if total_capacity <= 0:
        total_capacity = 1

    num_batches = min(len(cases), total_capacity)
    if num_batches == 0:
        return []

    batches = [[] for _ in range(num_batches)]
    for index, case in enumerate(cases):
        batches[index % num_batches].append(case)
    return [batch for batch in batches if batch]


def _run_finalize_hook(
    namespace: Dict[str, Any],
    results_dir: Optional[Path],
    task_results: Dict[str, Dict[str, Any]],
    extra_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Run ``beemesh_finalize`` if the script defines it."""

    finalize = namespace.get("beemesh_finalize")
    if not callable(finalize):
        return

    signature = inspect.signature(finalize)
    kwargs: Dict[str, Any] = {}
    if "results_dir" in signature.parameters:
        kwargs["results_dir"] = results_dir
    if "task_results" in signature.parameters:
        kwargs["task_results"] = task_results
    if extra_context:
        for key, value in extra_context.items():
            if key in signature.parameters:
                kwargs[key] = value
    finalize(**kwargs)


def _run_checkpoint_hook(
    namespace: Dict[str, Any],
    results_dir: Optional[Path],
    extra_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Run ``beemesh_checkpoint`` if the script defines it."""

    checkpoint = namespace.get("beemesh_checkpoint")
    if not callable(checkpoint):
        return

    signature = inspect.signature(checkpoint)
    kwargs: Dict[str, Any] = {}
    if "results_dir" in signature.parameters:
        kwargs["results_dir"] = results_dir
    if extra_context:
        for key, value in extra_context.items():
            if key in signature.parameters:
                kwargs[key] = value
    checkpoint(**kwargs)


def _run_live_hook(
    namespace: Dict[str, Any],
    results_dir: Optional[Path],
    task_results: Dict[str, Dict[str, Any]],
    pending_tasks: int,
) -> None:
    """Run ``beemesh_live_update`` if the script defines it."""

    live_update = namespace.get("beemesh_live_update")
    if not callable(live_update):
        return

    signature = inspect.signature(live_update)
    kwargs: Dict[str, Any] = {}
    if "results_dir" in signature.parameters:
        kwargs["results_dir"] = results_dir
    if "task_results" in signature.parameters:
        kwargs["task_results"] = task_results
    if "pending_tasks" in signature.parameters:
        kwargs["pending_tasks"] = pending_tasks
    live_update(**kwargs)


def _task_requirements_for_batch(
    namespace: Dict[str, Any],
    batch: List[Any],
) -> Dict[str, Any]:
    """Return task requirements for a batch, allowing script overrides."""

    default_requirements = {
        "preferred_device": "cpu",
        "min_cpu_cores": 1,
        "min_ram_gb": 0.25,
        "estimated_cost": max(1.0, round(len(batch) / 2.0, 2)),
    }

    requirements_fn = namespace.get("beemesh_task_requirements")
    if not callable(requirements_fn):
        return default_requirements

    custom = requirements_fn(batch)
    if not custom:
        return default_requirements

    merged = dict(default_requirements)
    merged.update(custom)
    return merged


def _evaluate_parallel_kwargs(
    namespace: Dict[str, Any],
    spec: ParallelSpec,
) -> Dict[str, Any]:
    """Evaluate keyword arguments passed to ``beemesh.parallel(...)``."""

    values: Dict[str, Any] = {}
    for key, expr in spec.parallel_kwargs.items():
        values[key] = eval(expr, namespace, namespace)
    return values


def _partition_axis(length: int, parts: int) -> List[tuple[int, int]]:
    """Partition an axis into nearly-equal half-open intervals."""

    base = length // parts
    remainder = length % parts
    intervals = []
    start = 0
    for index in range(parts):
        size = base + (1 if index < remainder else 0)
        end = start + size
        intervals.append((start, end))
        start = end
    return intervals


def _partition_axis_weighted(length: int, weights: List[float]) -> List[tuple[int, int]]:
    """Partition an axis into contiguous intervals proportional to positive weights."""

    if not weights:
        return [(0, length)]

    safe_weights = [max(float(weight), 0.1) for weight in weights]
    total = sum(safe_weights)
    raw_sizes = [length * weight / total for weight in safe_weights]
    sizes = [max(1, int(size)) for size in raw_sizes]

    assigned = sum(sizes)
    if assigned > length:
        overflow = assigned - length
        index = len(sizes) - 1
        while overflow > 0 and index >= 0:
            reducible = max(0, sizes[index] - 1)
            delta = min(reducible, overflow)
            sizes[index] -= delta
            overflow -= delta
            index -= 1
    elif assigned < length:
        remainder = length - assigned
        for index in range(remainder):
            sizes[index % len(sizes)] += 1

    intervals = []
    start = 0
    for size in sizes:
        end = start + size
        intervals.append((start, end))
        start = end
    if intervals:
        x0, _ = intervals[-1]
        intervals[-1] = (x0, length)
    return intervals


def _weighted_tile_assignment(
    workers: Dict[str, Dict[str, Any]],
    blocks_x: int,
    blocks_y: int,
) -> List[List[Optional[str]]]:
    """Assign checkerboard tiles to workers in score order using a snake walk."""

    alive = [
        (worker_id, info)
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    ]
    if not alive:
        return [[None for _ in range(blocks_y)] for _ in range(blocks_x)]

    alive = sorted(
        alive,
        key=lambda item: (
            -(float(item[1].get("performance_score", 1.0) or 1.0)),
            item[0],
        ),
    )
    worker_cycle = [worker_id for worker_id, _ in alive]

    tile_worker_ids: List[List[Optional[str]]] = [[None for _ in range(blocks_y)] for _ in range(blocks_x)]
    tile_index = 0
    for tile_x in range(blocks_x):
        y_indices = range(blocks_y) if tile_x % 2 == 0 else range(blocks_y - 1, -1, -1)
        for tile_y in y_indices:
            tile_worker_ids[tile_x][tile_y] = worker_cycle[tile_index % len(worker_cycle)]
            tile_index += 1
    return tile_worker_ids


def _build_partition_overlays(
    x_parts: List[tuple[int, int]],
    y_parts: List[tuple[int, int]],
    workers: Dict[str, Dict[str, Any]],
    tile_worker_ids: List[List[Optional[str]]],
) -> List[Dict[str, Any]]:
    """Attach lightweight worker metadata to each 2D tile for later visualization."""

    overlays: List[Dict[str, Any]] = []
    for tile_x, (x0, x1) in enumerate(x_parts):
        for tile_y, (y0, y1) in enumerate(y_parts):
            worker_id = None
            if tile_x < len(tile_worker_ids) and tile_y < len(tile_worker_ids[tile_x]):
                worker_id = tile_worker_ids[tile_x][tile_y]
            worker_info = workers.get(worker_id, {}) if worker_id else {}
            overlays.append(
                {
                    "x0": x0,
                    "x1": x1,
                    "y0": y0,
                    "y1": y1,
                    "worker_id": worker_id,
                    "hostname": worker_info.get("hostname") or worker_id or "unassigned",
                    "cpu_cores": worker_info.get("cpu_cores"),
                    "ram_gb": worker_info.get("ram_gb"),
                    "gpu": worker_info.get("gpu"),
                    "gpu_memory_gb": worker_info.get("gpu_memory_gb"),
                    "architecture": worker_info.get("architecture"),
                    "performance_score": worker_info.get("performance_score"),
                }
            )
    return overlays


def _choose_grid_partitions(num_workers: int, nx: int, ny: int) -> tuple[int, int]:
    """Choose a simple near-square block decomposition."""

    import math

    target = max(1, num_workers * 3)
    best = (1, target)
    best_score = float("inf")
    aspect = max(nx, 1) / max(ny, 1)

    for blocks_x in range(1, min(target, nx) + 1):
        blocks_y = math.ceil(target / blocks_x)
        if blocks_y > ny:
            continue
        tile_aspect = (nx / blocks_x) / max(ny / blocks_y, 1e-12)
        shape_penalty = abs(math.log(max(tile_aspect, 1e-12) / max(aspect, 1e-12)))
        extra_tiles = blocks_x * blocks_y - target
        score = shape_penalty + 0.08 * extra_tiles
        if score < best_score:
            best = (blocks_x, blocks_y)
            best_score = score

    return best


def _weighted_worker_strips(
    length: int,
    workers: Dict[str, Dict[str, Any]],
) -> List[tuple[str, int, int]]:
    """Split an axis into weighted strips based on worker performance."""

    alive = [
        (worker_id, info)
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    ]
    if not alive:
        return []

    alive = sorted(
        alive,
        key=lambda item: (
            -(float(item[1].get("performance_score", 1.0) or 1.0)),
            item[0],
        ),
    )
    count = min(len(alive), max(1, length))
    selected = alive[:count]

    weights = [max(float(info.get("performance_score", 1.0) or 1.0), 0.1) for _, info in selected]
    total = sum(weights)
    raw_sizes = [length * weight / total for weight in weights]
    sizes = [max(1, int(size)) for size in raw_sizes]

    assigned = sum(sizes)
    if assigned > length:
        overflow = assigned - length
        index = len(sizes) - 1
        while overflow > 0 and index >= 0:
            reducible = max(0, sizes[index] - 1)
            delta = min(reducible, overflow)
            sizes[index] -= delta
            overflow -= delta
            index -= 1
    elif assigned < length:
        remainder = length - assigned
        for index in range(remainder):
            sizes[index % len(sizes)] += 1

    strips = []
    start = 0
    for (worker_id, _), size in zip(selected, sizes):
        end = start + size
        strips.append((worker_id, start, end))
        start = end

    if strips:
        worker_id, x0, _ = strips[-1]
        strips[-1] = (worker_id, x0, length)
    return strips


def _extract_periodic_tile(u, x0: int, x1: int, y0: int, y1: int, ghost: int = 1):
    """Extract a tile with periodic ghost cells from a global field."""

    import numpy as np

    x_indices = [(idx % u.shape[0]) for idx in range(x0 - ghost, x1 + ghost)]
    y_indices = [(idx % u.shape[1]) for idx in range(y0 - ghost, y1 + ghost)]
    tile = np.take(np.take(u, x_indices, axis=0), y_indices, axis=1)
    return tile


def _wait_for_task_results(
    hive_url: str,
    task_ids: set[str],
    wait_interval: float,
) -> Dict[str, Dict[str, Any]]:
    """Poll the Hive until all requested task ids have results."""

    import requests
    import time

    pending = set(task_ids)
    completed_results: Dict[str, Dict[str, Any]] = {}
    while pending:
        results_response = requests.get(f"{hive_url}/results", timeout=30)
        results_response.raise_for_status()
        results = results_response.json()

        finished = pending.intersection(results)
        for task_id in sorted(finished):
            result = results[task_id]
            if result.get("success") is False:
                error = result.get("error", "worker-side task failed")
                traceback_text = result.get("traceback")
                message = f"BeeMesh task {task_id} failed: {error}"
                if traceback_text:
                    message += f"\n\n{traceback_text}"
                raise RuntimeError(message)
            completed_results[task_id] = result
            pending.remove(task_id)

        if pending:
            time.sleep(wait_interval)
    return completed_results


def _measure_hive_latency(hive_url: str) -> Optional[float]:
    """Measure a simple Hive round-trip time using the status endpoint."""

    import requests
    import time

    try:
        start = time.perf_counter()
        response = requests.get(f"{hive_url}/status", timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return None
    return time.perf_counter() - start


def _results_subdir_for_script(script_path: str) -> str:
    """Return a repo-relative server_results path for a launched script."""

    repo_root = Path(__file__).resolve().parent.parent
    script_dir = Path(script_path).resolve().parent
    try:
        return str(script_dir.relative_to(repo_root) / "server_results")
    except ValueError:
        return ""


def _launch_grid_script(
    spec: ParallelSpec,
    launch_context: LaunchContext,
    hive_url: str,
    auth_token: str,
    wait_interval: float,
    workers: Dict[str, Dict[str, Any]],
    script_path: str,
) -> None:
    """Launch a coupled structured-grid PDE job with ghost exchange."""

    import numpy as np
    import requests
    import time

    parallel_kwargs = _evaluate_parallel_kwargs(launch_context.namespace, spec)
    if "grid" not in parallel_kwargs:
        raise ValueError("Grid launch requires beemesh.parallel(grid=<field>).")

    grid_workload = launch_context.namespace.get("beemesh_grid_workload")
    if grid_workload not in {"advection2d", "acoustic_pulse2d"}:
        raise ValueError(
            "Grid launch currently supports only beemesh_grid_workload = "
            "'advection2d' or 'acoustic_pulse2d'."
        )

    u = np.asarray(parallel_kwargs["grid"], dtype=float)
    if u.ndim != 2:
        raise ValueError("Grid launch currently requires a 2D NumPy-like field.")

    steps = len(launch_context.cases)
    if steps == 0:
        print("No time steps requested. Nothing to launch.")
        return

    active_workers = [
        worker_id
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    ]
    blocks_x = launch_context.namespace.get("beemesh_grid_blocks_x")
    blocks_y = launch_context.namespace.get("beemesh_grid_blocks_y")
    weighted_strips = None
    if blocks_x is None and blocks_y is None:
        weighted_strips = _weighted_worker_strips(u.shape[0], workers)
        blocks_x = len(weighted_strips) if weighted_strips else 1
        blocks_y = 1
    elif blocks_x is None or blocks_y is None:
        blocks_x, blocks_y = _choose_grid_partitions(max(len(active_workers), 1), *u.shape)

    dx = float(launch_context.namespace["dx"])
    dy = float(launch_context.namespace["dy"])
    dt = float(launch_context.namespace["dt"])
    if grid_workload == "advection2d":
        c_x = float(launch_context.namespace["c_x"])
        c_y = float(launch_context.namespace["c_y"])
        prev_u = None
        wave_speed = None
    else:
        c_x = c_y = None
        prev_u = np.asarray(launch_context.namespace["beemesh_prev_grid"], dtype=float)
        if prev_u.shape != u.shape:
            raise ValueError("beemesh_prev_grid must have the same shape as grid.")
        wave_speed = float(launch_context.namespace["wave_speed"])

    results_subdir = _results_subdir_for_script(script_path)

    if weighted_strips is not None:
        x_parts = [(x0, x1) for _, x0, x1 in weighted_strips]
        y_parts = [(0, u.shape[1])]
        tile_worker_ids = [[worker_id] for worker_id, _, _ in weighted_strips]
    else:
        x_parts = _partition_axis(u.shape[0], int(blocks_x))
        y_parts = _partition_axis(u.shape[1], int(blocks_y))
        tile_worker_ids = _weighted_tile_assignment(workers, int(blocks_x), int(blocks_y))
    partition_overlays = _build_partition_overlays(x_parts, y_parts, workers, tile_worker_ids)
    step_history = []
    snapshot_interval = int(
        launch_context.namespace.get("beemesh_snapshot_interval", max(1, steps // 12 or 1))
    )
    frame_snapshots = [{"step": 0, "field": u.copy()}]
    latest_results_dir: Optional[Path] = None
    launch_id = uuid.uuid4().hex[:8]

    print(
        f"Launching coupled grid job ({grid_workload}): {u.shape[0]}x{u.shape[1]} field, "
        f"{steps} step(s), {blocks_x}x{blocks_y} tiles across {len(active_workers)} bee(s)."
    )
    if weighted_strips is not None:
        print("Strength-weighted strips:")
        for worker_id, x0, x1 in weighted_strips:
            worker_info = workers.get(worker_id, {})
            hostname = worker_info.get("hostname", worker_id)
            score = worker_info.get("performance_score", "?")
            print(f"  {hostname} ({worker_id}) score={score} -> x[{x0}:{x1}]")
    else:
        print("Checkerboard tile assignment:")
        for tile_x, (x0, x1) in enumerate(x_parts):
            for tile_y, (y0, y1) in enumerate(y_parts):
                worker_id = tile_worker_ids[tile_x][tile_y]
                worker_info = workers.get(worker_id, {})
                hostname = worker_info.get("hostname", worker_id)
                print(f"  tile ({tile_x},{tile_y}) x[{x0}:{x1}] y[{y0}:{y1}] -> {hostname} ({worker_id})")

    for step_index in range(steps):
        step_ping_s = _measure_hive_latency(hive_url)
        tasks = []
        for tile_x, (x0, x1) in enumerate(x_parts):
            for tile_y, (y0, y1) in enumerate(y_parts):
                target_worker_id = tile_worker_ids[tile_x][tile_y]
                tile = _extract_periodic_tile(u, x0, x1, y0, y1, ghost=1)
                payload = {
                    "grid_workload": grid_workload,
                    "step_index": step_index,
                    "tile_x": tile_x,
                    "tile_y": tile_y,
                    "x0": x0,
                    "x1": x1,
                    "y0": y0,
                    "y1": y1,
                    "tile": tile.tolist(),
                    "dx": dx,
                    "dy": dy,
                    "dt": dt,
                    "ghost": 1,
                }
                if grid_workload == "advection2d":
                    payload["c_x"] = c_x
                    payload["c_y"] = c_y
                else:
                    prev_tile = _extract_periodic_tile(prev_u, x0, x1, y0, y1, ghost=1)
                    payload["prev_tile"] = prev_tile.tolist()
                    payload["wave_speed"] = wave_speed
                tile_nx = x1 - x0
                tile_ny = y1 - y0
                task_id = (
                    f"{grid_workload}_{launch_id}_step_{step_index}_tile_{tile_x}_{tile_y}"
                )
                tasks.append(
                    {
                        "task_id": task_id,
                        "task_type": "pde_timestep_tile",
                        "payload": payload,
                        "requirements": {
                            "preferred_device": "cpu",
                            "min_cpu_cores": 1,
                            "min_ram_gb": max(0.25, round(tile_nx * tile_ny * 8 / (1024**3), 3)),
                            "estimated_cost": max(1.0, round(tile_nx * tile_ny / 2500.0, 2)),
                            "target_worker_id": target_worker_id,
                        },
                    }
                )

        preflight_worker_fit(tasks, workers)
        submit_payload = {
            "job_type": grid_workload,
            "payload": {
                "tasks": tasks,
                "results_subdir": results_subdir,
            },
            "auth_token": auth_token,
        }
        submit_started = time.perf_counter()
        submit_response = requests.post(
            f"{hive_url}/submit_job",
            json=submit_payload,
            timeout=30,
        )
        submit_response.raise_for_status()
        submit_duration_s = time.perf_counter() - submit_started
        task_ids = {task["task_id"] for task in tasks}
        print(
            f"Step {step_index + 1}/{steps}: dispatched {len(task_ids)} tile task(s)."
        )
        wait_started = time.perf_counter()
        step_results = _wait_for_task_results(hive_url, task_ids, wait_interval)
        wait_duration_s = time.perf_counter() - wait_started

        new_u = np.empty_like(u)
        result_paths = []
        for task_id, result in step_results.items():
            if result.get("__beemesh_result_file__"):
                result_paths.append(Path(result["__beemesh_result_file__"]))
            interior = np.asarray(result["interior"], dtype=float)
            x0 = int(result["x0"])
            x1 = int(result["x1"])
            y0 = int(result["y0"])
            y1 = int(result["y1"])
            new_u[x0:x1, y0:y1] = interior

        if grid_workload == "acoustic_pulse2d":
            prev_u = u
        u = new_u
        latest_results_dir = result_paths[0].parent if result_paths else latest_results_dir
        step_history.append(
            {
                "step": step_index + 1,
                "tasks": len(task_ids),
                "mean": float(np.mean(u)),
                "max": float(np.max(u)),
                "min": float(np.min(u)),
                "hive_ping_s": step_ping_s,
                "submit_duration_s": submit_duration_s,
                "wait_duration_s": wait_duration_s,
                "network_overhead_s": (step_ping_s or 0.0) + submit_duration_s,
            }
        )
        if (
            (step_index + 1) % snapshot_interval == 0
            or step_index == steps - 1
        ):
            frame_snapshots.append({"step": step_index + 1, "field": u.copy()})
        _run_checkpoint_hook(
            launch_context.namespace,
            latest_results_dir,
            extra_context={
                "final_grid": u,
                "step_history": step_history,
                "frame_snapshots": frame_snapshots,
                "tile_partitions": {
                    "x_parts": x_parts,
                    "y_parts": y_parts,
                    "partition_overlays": partition_overlays,
                },
            },
        )

    _run_finalize_hook(
        launch_context.namespace,
        latest_results_dir,
        {},
        extra_context={
            "final_grid": u,
            "step_history": step_history,
            "frame_snapshots": frame_snapshots,
            "tile_partitions": {
                "x_parts": x_parts,
                "y_parts": y_parts,
                "partition_overlays": partition_overlays,
            },
        },
    )


def _print_monitor_hint(hive_url: str) -> None:
    """Print a standout monitor command hint for the current launch."""

    command = f"beemesh monitor --hive-url {hive_url}"
    border = "=" * max(len(command), 24)
    print("\nMonitor Command")
    print(border)
    print(command)
    print(border)
    print("Press Ctrl+C to stop waiting here and run the monitor command.")


def preflight_worker_fit(
    tasks: List[Dict[str, Any]],
    workers: Dict[str, Dict[str, Any]],
) -> None:
    """Fail early when no alive worker can satisfy a task's requirements."""

    alive_workers = {
        worker_id: info
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    }
    if not alive_workers:
        raise RuntimeError("No alive workers are registered with the Hive.")

    failures = []
    for task in tasks:
        if any(
            worker_can_run_task(info, task, worker_id=worker_id)
            for worker_id, info in alive_workers.items()
        ):
            continue

        requirements = task.get("requirements", {})
        failures.append(
            f"{task['task_id']}: no eligible bee satisfies requirements {requirements}"
        )

    if failures:
        message = "Launch rejected because some tasks cannot run on the current bees:\n"
        message += "\n".join(f"- {failure}" for failure in failures[:5])
        if len(failures) > 5:
            message += f"\n- ... and {len(failures) - 5} more"
        raise RuntimeError(message)


def launch_script(
    script_path: str,
    hive_url: str,
    auth_token: str,
    wait_interval: float = 2.0,
    live: bool = False,
) -> None:
    """Launch a script's BeeMesh parallel loop onto the active worker pool."""
    import requests

    spec = extract_parallel_spec(script_path)

    try:
        status_response = requests.get(f"{hive_url}/status", timeout=30)
        status_response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the Hive at {hive_url}.") from exc

    workers = status_response.json().get("workers", {})
    if not workers:
        raise RuntimeError("No workers are registered with the Hive.")

    launch_context = _load_cases(script_path, spec)
    cases = launch_context.cases
    if not cases:
        print("No cases found in the parallel iterable. Nothing to launch.")
        return

    if "grid" in spec.parallel_kwargs:
        _launch_grid_script(
            spec,
            launch_context,
            hive_url,
            auth_token,
            wait_interval,
            workers,
            script_path,
        )
        return

    active_workers = [
        worker_id
        for worker_id, info in workers.items()
        if info.get("status", "alive") == "alive"
    ]
    results_subdir = _results_subdir_for_script(script_path)

    batches = _build_batches(cases, workers)
    launch_id = uuid.uuid4().hex[:8]
    tasks = []
    for index, batch in enumerate(batches):
        tasks.append(
            {
                "task_id": f"python_batch_{launch_id}_{index}",
                "task_type": "python_batch",
                "payload": {
                    "script_path": Path(script_path).name,
                    "prelude_source": spec.prelude_source,
                    "loop_target": spec.loop_target,
                    "loop_body": spec.loop_body,
                    "cases": batch,
                    "captured_inputs": launch_context.captured_inputs,
                },
                "requirements": _task_requirements_for_batch(
                    launch_context.namespace,
                    batch,
                ),
            }
        )

    preflight_worker_fit(tasks, workers)

    submit_payload = {
        "job_type": "python_batch",
        "payload": {
            "tasks": tasks,
            "results_subdir": results_subdir,
        },
        "auth_token": auth_token,
    }
    submit_response = requests.post(
        f"{hive_url}/submit_job",
        json=submit_payload,
        timeout=30,
    )
    submit_response.raise_for_status()
    job = submit_response.json()
    print("Launch response:")
    print(job)
    print(f"Dispatched across {len(active_workers)} bee(s).")
    _print_monitor_hint(hive_url)

    task_ids = {task["task_id"] for task in tasks}
    pending = set(task_ids)
    completed_results: Dict[str, Dict[str, Any]] = {}
    print(f"Waiting for {len(task_ids)} remote batch tasks to finish...")

    try:
        while pending:
            results_response = requests.get(f"{hive_url}/results", timeout=30)
            results_response.raise_for_status()
            results = results_response.json()

            finished = pending.intersection(results)
            new_results = False
            for task_id in sorted(finished):
                result = results[task_id]
                completed_results[task_id] = result
                new_results = True
                print(f"\n[{task_id}] cases={result.get('cases_processed')}")
                if result.get("__beemesh_result_file__"):
                    print(f"saved={result['__beemesh_result_file__']}")
                if result.get("stdout"):
                    print(
                        result["stdout"],
                        end="" if result["stdout"].endswith("\n") else "\n",
                    )
                if result.get("stderr"):
                    print(
                        result["stderr"],
                        end="" if result["stderr"].endswith("\n") else "\n",
                    )
                pending.remove(task_id)

            if live and new_results:
                result_paths = [
                    Path(result["__beemesh_result_file__"])
                    for result in completed_results.values()
                    if result.get("__beemesh_result_file__")
                ]
                results_dir = result_paths[0].parent if result_paths else None
                _run_live_hook(
                    launch_context.namespace,
                    results_dir,
                    completed_results,
                    len(pending),
                )

            if pending:
                import time

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
    _run_finalize_hook(launch_context.namespace, results_dir, completed_results)
