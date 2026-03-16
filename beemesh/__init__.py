from contextlib import AbstractContextManager

from beemesh.version import __version__


class _ParallelContext(AbstractContextManager):
    """Marker context used by ``beemesh --launch`` AST extraction."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __exit__(self, exc_type, exc, exc_tb):
        return False


def parallel(**kwargs):
    """Mark a loop for BeeMesh launch-time parallelization."""

    return _ParallelContext(**kwargs)


def swarm(**kwargs):
    """Bee-themed alias for ``parallel()``."""

    return parallel(**kwargs)


__all__ = ["__version__", "parallel", "swarm"]
