from __future__ import annotations


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Synthia"
    assert "version" in body


def test_ready_reports_dependencies(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["demo_mode"] is True
    names = {dep["name"] for dep in body["dependencies"]}
    assert {"llm", "stt", "provider:aws", "provider:docker", "provider:azure"} <= names


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["tagline"] == "Speak to your infrastructure."
