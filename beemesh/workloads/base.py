"""
Minimal workload interface for built-in BeeMesh task handlers.

Most current workloads are simple functions registered in the worker executor.
This base class remains as a small placeholder for future class-based workload
implementations.
"""


class Workload:
    """
    Minimal interface for a class-based workload implementation.
    """

    name = "base"

    def run(self, payload):
        raise NotImplementedError
