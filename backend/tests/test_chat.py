from __future__ import annotations


def test_general_conversation_routes_to_demo_llm(client):
    response = client.post(
        "/api/chat",
        json={"message": "hello synthia, how are you?", "mode": "general"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "conversation"
    assert body["provider_used"] == "demo"
    assert body["reply"]
    assert body["tool_call"] is None


def test_general_mode_does_not_execute_tools(client):
    response = client.post(
        "/api/chat",
        json={"message": "list containers", "mode": "general"},
    )
    assert response.status_code == 200
    assert response.json()["tool_call"] is None


def test_cloud_mode_runs_read_only_demo_tool(client):
    response = client.post(
        "/api/chat", json={"message": "List my EC2 instances", "mode": "cloud"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "read_only"
    assert body["tool_call"]["name"] == "demo.list_ec2_instances"
    assert body["tool_call"]["simulated"] is True
    assert body["tool_call"]["result"]["count"] == 2
    assert "DEMO" in body["reply"]


def test_cloud_explanation_is_conversational(client):
    response = client.post(
        "/api/chat",
        json={
            "message": "Explain the difference between an EC2 instance and a container",
            "mode": "cloud",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "explanation"
    assert body["tool_call"] is None


def test_blank_message_rejected(client):
    response = client.post("/api/chat", json={"message": "   ", "mode": "general"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_history_is_accepted(client):
    response = client.post(
        "/api/chat",
        json={
            "message": "and what about S3?",
            "mode": "general",
            "history": [
                {"role": "user", "content": "tell me about EC2"},
                {"role": "assistant", "content": "EC2 is ..."},
            ],
        },
    )
    assert response.status_code == 200
