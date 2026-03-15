"""
Submit a diffusion job to the BeeMesh Hive.

This example script creates multiple diffusion tasks and sends them to the coordinator.
"""
import requests

HIVE_URL = "http://127.0.0.1:8000"


def submit_diffusion_job():

    tasks = []

    # create a batch of independent diffusion tasks
    for i in range(20):
        task = {
            "task_id": f"diffusion_task_{i}",
            "task_type": "diffusion",
            "payload": {
                "nx": 64,
                "ny": 64,
                "steps": 2000,
                "alpha": 0.1,
            },
        }
        tasks.append(task)

    job = {
        "job_type": "diffusion",
        "payload": {"tasks": tasks},
    }

    r = requests.post(f"{HIVE_URL}/submit_job", json=job)

    print(r.json())


if __name__ == "__main__":
    submit_diffusion_job()
