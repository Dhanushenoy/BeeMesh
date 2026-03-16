import base64

import pytest

from beemesh.worker.executor import execute_task
from beemesh.workloads.executable_batch import run_executable_batch_task
from beemesh.workloads.pde_timestep_tile import run_pde_timestep_tile_task
from beemesh.workloads.python_batch import run_python_batch_task


def test_execute_task_rejects_unknown_task_type():
    with pytest.raises(ValueError, match="Unknown task type"):
        execute_task({"task_type": "missing", "payload": {}})


def test_python_batch_task_executes_cases_and_captures_stdout():
    result = run_python_batch_task(
        {
            "script_path": "demo.py",
            "prelude_source": "scale = 3\n",
            "loop_target": "case",
            "loop_body": "print(case * scale)",
            "cases": [1, 2],
        }
    )

    assert result["success"] is True
    assert result["cases_processed"] == 2
    assert "3" in result["stdout"]
    assert "6" in result["stdout"]


def test_python_batch_task_reports_failure_in_stderr():
    result = run_python_batch_task(
        {
            "script_path": "demo.py",
            "loop_target": "case",
            "loop_body": "raise RuntimeError('boom')",
            "cases": [1],
        }
    )

    assert result["success"] is False
    assert "RuntimeError" in result["stderr"]


def test_pde_timestep_tile_returns_interior_metadata():
    payload = {
        "step_index": 0,
        "tile_x": 0,
        "tile_y": 0,
        "x0": 0,
        "x1": 2,
        "y0": 0,
        "y1": 2,
        "tile": [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 2.0, 0.0],
            [0.0, 3.0, 4.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ],
        "c_x": 1.0,
        "c_y": 0.0,
        "dx": 1.0,
        "dy": 1.0,
        "dt": 0.1,
        "ghost": 1,
    }

    result = run_pde_timestep_tile_task(payload)

    assert result["step_index"] == 0
    assert result["x0"] == 0
    assert result["x1"] == 2
    assert len(result["interior"]) == 2
    assert len(result["interior"][0]) == 2


def test_executable_batch_task_runs_uploaded_script_cases():
    script = "\n".join(
        [
            "#!/bin/sh",
            "echo \"case:$1\"",
        ]
    )
    payload = {
        "executable_name": "simulate_case.sh",
        "executable_blob_b64": base64.b64encode(script.encode("utf-8")).decode("ascii"),
        "cases": [1, 2],
    }

    result = run_executable_batch_task(payload)

    assert result["success"] is True
    assert result["cases_processed"] == 2
    assert result["outputs"][0]["stdout"].strip() == "case:1"
    assert result["outputs"][1]["stdout"].strip() == "case:2"
