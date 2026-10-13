from __future__ import annotations


def test_execute_read_only_demo_tool(client):
    response = client.post(
        "/api/tools/execute",
        json={"name": "demo.list_containers", "arguments": {"all": True}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["result"]["count"] == 2
    assert body["read_only"] is True


def test_execute_unknown_tool(client):
    response = client.post(
        "/api/tools/execute", json={"name": "shell.exec", "arguments": {}}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_tool"


def test_execute_invalid_arguments(client):
    response = client.post(
        "/api/tools/execute",
        json={"name": "demo.list_ec2_instances", "arguments": {"nope": 1}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_tool_arguments"


def test_execute_mutating_denied_by_default(client):
    # V1 defaults to read-only, so mutating tools are denied even when confirmed.
    blocked = client.post(
        "/api/tools/execute",
        json={
            "name": "demo.simulated_action",
            "arguments": {"action": "x", "target": "demo"},
            "confirmed": True,
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "permission_denied"


def test_execute_mutating_allowed_when_opted_in(make_client):
    client = make_client(ALLOW_MUTATING="true")
    response = client.post(
        "/api/tools/execute",
        json={
            "name": "demo.simulated_action",
            "arguments": {"action": "restart", "target": "synthia-api"},
            "confirmed": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["result"]["performed"] is False
