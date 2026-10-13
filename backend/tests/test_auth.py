from __future__ import annotations


def test_general_chat_open_but_tools_protected(make_client):
    client = make_client(API_AUTH_TOKEN="s3cret-token")

    general = client.post("/api/chat", json={"message": "hello", "mode": "general"})
    assert general.status_code == 200

    blocked = client.post(
        "/api/chat", json={"message": "list ec2 instances", "mode": "cloud"}
    )
    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "unauthorized"

    allowed = client.post(
        "/api/chat",
        json={"message": "list ec2 instances", "mode": "cloud"},
        headers={"Authorization": "Bearer s3cret-token"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["tool_call"]["name"] == "demo.list_ec2_instances"


def test_wrong_token_rejected(make_client):
    client = make_client(API_AUTH_TOKEN="right")
    response = client.post(
        "/api/chat",
        json={"message": "list containers", "mode": "cloud"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_transcriptions_protected_when_token_set(make_client):
    client = make_client(API_AUTH_TOKEN="tok")
    assert client.get("/api/transcriptions").status_code == 401

    created = client.post(
        "/api/transcriptions",
        json={"transcript": "hi", "status": "success"},
        headers={"Authorization": "Bearer tok"},
    )
    assert created.status_code == 200
    listing = client.get(
        "/api/transcriptions", headers={"Authorization": "Bearer tok"}
    )
    assert listing.status_code == 200


def test_rate_limit_enforced(make_client):
    client = make_client(RATE_LIMIT_PER_MINUTE="2")
    assert client.post("/api/chat", json={"message": "one", "mode": "general"}).status_code == 200
    assert client.post("/api/chat", json={"message": "two", "mode": "general"}).status_code == 200
    third = client.post("/api/chat", json={"message": "three", "mode": "general"})
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
