"""
BeeMesh Scheduler

Responsible for deciding which task should be given to a worker.
For v0 we simply use FIFO.
"""

def schedule(task_queue):
    """
    Return the next task to execute.
    """
    if not task_queue:
        return None

    return task_queue.pop(0)