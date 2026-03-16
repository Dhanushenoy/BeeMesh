"""
BeeMesh Python batch workload.

Executes a batch of cases by replaying the script prelude and loop body shipped
by ``beemesh --launch``.
"""

import contextlib
import io
import textwrap
import traceback
from typing import Any, Dict


def run_python_batch_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Python loop body against a remote batch of case values."""

    script_path = payload.get("script_path", "<beemesh-script>")
    prelude_source = payload.get("prelude_source", "")
    loop_target = payload.get("loop_target", "case")
    loop_body = payload.get("loop_body", "")
    cases = payload.get("cases", [])
    captured_inputs = list(payload.get("captured_inputs", []))

    def replay_input(prompt: str = "") -> str:
        prompt_text = str(prompt)
        if captured_inputs:
            next_input = captured_inputs.pop(0)
            if next_input.get("prompt") == prompt_text:
                return next_input.get("response", "")
            return next_input.get("response", "")
        return ""

    namespace: Dict[str, Any] = {
        "__file__": script_path,
        "__name__": "__beemesh_worker__",
        "__beemesh_cases__": cases,
        "input": replay_input,
    }
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    success = True

    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
            stderr_buffer
        ):
            if prelude_source.strip():
                exec(compile(prelude_source, script_path, "exec"), namespace, namespace)
            runner_source = f"for {loop_target} in __beemesh_cases__:\n"
            if loop_body:
                runner_source += textwrap.indent(loop_body, "    ")
            else:
                runner_source += "    pass\n"
            exec(
                compile(runner_source, f"{script_path}<parallel>", "exec"),
                namespace,
                namespace,
            )
    except Exception:
        success = False
        traceback.print_exc(file=stderr_buffer)

    return {
        "cases_processed": len(cases),
        "stdout": stdout_buffer.getvalue(),
        "stderr": stderr_buffer.getvalue(),
        "success": success,
    }
