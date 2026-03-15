"""
BeeMesh Workload Base Class
"""

class Workload:
    """
    Base class for all BeeMesh workloads.
    """

    name = "base"

    def run(self, payload):
        raise NotImplementedError