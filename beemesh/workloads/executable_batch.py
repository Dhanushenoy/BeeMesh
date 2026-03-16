"""
BeeMesh workload for running shipped native executables over a case sweep.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Any, Dict


def run_executable_batch_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run an uploaded executable once per scalar case value."""

    executable_name = payload.get("executable_name", "beemesh_exec")
    executable_blob_b64 = payload.get("executable_blob_b64", "")
    cases = payload.get("cases", [])

    if not executable_blob_b64:
        raise ValueError("Executable batch payload is missing executable bytes.")

    executable_bytes = base64.b64decode(executable_blob_b64.encode("ascii"))
    outputs = []
    success = True

    with tempfile.TemporaryDirectory(prefix="beemesh-exec-") as tmpdir:
        exec_path = Path(tmpdir) / executable_name
        exec_path.write_bytes(executable_bytes)
        exec_path.chmod(exec_path.stat().st_mode | stat.S_IEXEC)

        for case in cases:
            completed = subprocess.run(
                [os.fspath(exec_path), str(case)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                success = False
            outputs.append(
                {
                    "case": case,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )

    return {
        "cases_processed": len(cases),
        "outputs": outputs,
        "success": success,
    }
