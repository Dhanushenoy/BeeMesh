import pytest
from fastapi.testclient import TestClient

import beemesh.coordinator.server as server
from beemesh.coordinator.state import HiveState


@pytest.fixture
def client(tmp_path, monkeypatch):
    results_dir = tmp_path / "server_results"
    results_dir.mkdir()

    monkeypatch.setattr(server, "state", HiveState())
    monkeypatch.setattr(server, "jobs", {})
    monkeypatch.setattr(server, "task_to_job", {})
    monkeypatch.setattr(server, "job_result_roots", {})
    monkeypatch.setattr(server, "job_submitted", 0)
    monkeypatch.setattr(server, "WORKER_AUTH_TOKEN", "worker-token")
    monkeypatch.setattr(server, "CLIENT_AUTH_TOKEN", "client-token")
    monkeypatch.setattr(server, "RESULTS_DIR", results_dir)

    return TestClient(server.app)


def test_register_worker_rejects_invalid_auth(client):
    response = client.post(
        "/register_worker",
        json={
            "hostname": "bee-1",
            "cpu_cores": 4,
            "ram_gb": 8.0,
            "gpu": None,
            "gpu_memory_gb": 0.0,
            "architecture": "x86_64",
            "auth_token": "wrong-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid worker auth token"


def test_submit_job_rejects_invalid_client_auth(client):
    response = client.post(
        "/submit_job",
        json={
            "job_type": "python_batch",
            "payload": {"tasks": []},
            "auth_token": "wrong-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid client auth token"


def test_submit_result_rejects_wrong_worker_for_leased_task(client):
    worker_1 = server.state.register_worker("bee-1", cpu_cores=1, ram_gb=4.0)
    worker_2 = server.state.register_worker("bee-2", cpu_cores=1, ram_gb=4.0)
    task = {"task_id": "task-1", "task_type": "python_batch", "payload": {}}
    server.state.add_task(task)
    server.state.lease_task(worker_1)

    response = client.post(
        "/submit_result",
        json={
            "worker_id": worker_2,
            "task_id": "task-1",
            "result": {"success": True},
            "auth_token": "worker-token",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Task is leased to a different worker."


def test_submit_job_rejects_malformed_manual_tasks(client):
    response = client.post(
        "/submit_job",
        json={
            "job_type": "python_batch",
            "payload": {
                "tasks": [
                    {
                        "task_type": "python_batch",
                        "payload": {},
                    }
                ]
            },
            "auth_token": "client-token",
        },
    )

    assert response.status_code == 400
    assert "task_id" in response.json()["detail"]


def test_results_endpoint_can_filter_by_job_id(client):
    server.state.results = {
        "task-1": {"success": True},
        "task-2": {"success": False},
    }
    server.task_to_job["task-1"] = "job_1"
    server.task_to_job["task-2"] = "job_2"

    response = client.get("/results", params={"job_id": "job_1"})

    assert response.status_code == 200
    assert response.json() == {"task-1": {"success": True}}
