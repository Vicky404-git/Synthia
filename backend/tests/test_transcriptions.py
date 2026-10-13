from __future__ import annotations

FAILURE_STATUSES = [
    "empty_transcript",
    "permission_denied",
    "unsupported_browser",
    "network_failure",
    "provider_error",
    "timeout",
    "parse_failed",
    "tool_failed",
]


def test_create_and_list_transcription(client):
    created = client.post(
        "/api/transcriptions",
        json={
            "transcript": "show all containers",
            "provider": "browser-webspeech",
            "language": "en-US",
            "source": "speech",
            "status": "success",
            "confidence": 0.92,
            "parsed_intent": "list_containers",
            "tool_name": "docker.list_containers",
            "tool_status": "tool_succeeded",
            "duration_ms": 820,
        },
    )
    assert created.status_code == 200
    event = created.json()
    assert event["event_id"]
    assert event["transcript"] == "show all containers"

    listing = client.get("/api/transcriptions").json()
    assert listing["count"] == 1
    assert listing["persistence"] == "in-memory (ephemeral)"
    assert listing["events"][0]["event_id"] == event["event_id"]


def test_get_transcription_by_id_and_404(client):
    created = client.post(
        "/api/transcriptions",
        json={"transcript": "hi", "status": "success"},
    ).json()
    ok = client.get(f"/api/transcriptions/{created['event_id']}")
    assert ok.status_code == 200
    missing = client.get("/api/transcriptions/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "validation_error"


def test_failure_statuses_are_distinct(client):
    for status in FAILURE_STATUSES:
        response = client.post(
            "/api/transcriptions",
            json={
                "transcript": "",
                "status": status,
                "source": "speech",
                "error": {"code": status, "message": f"simulated {status}"},
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == status

    events = client.get("/api/transcriptions").json()["events"]
    assert {e["status"] for e in events} == set(FAILURE_STATUSES)


def test_typed_input_is_labelled(client):
    created = client.post(
        "/api/transcriptions",
        json={"transcript": "list s3 buckets", "status": "success", "source": "typed"},
    ).json()
    assert created["source"] == "typed"


def test_invalid_status_rejected(client):
    response = client.post(
        "/api/transcriptions",
        json={"transcript": "x", "status": "something_went_wrong"},
    )
    assert response.status_code == 422


def test_clear_transcriptions(client):
    client.post("/api/transcriptions", json={"transcript": "a", "status": "success"})
    cleared = client.delete("/api/transcriptions")
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] == 1
    assert client.get("/api/transcriptions").json()["count"] == 0


def test_stt_unconfigured_reports_honestly(client):
    response = client.post(
        "/api/stt/transcribe",
        files={"file": ("audio.webm", b"fake-bytes", "audio/webm")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_not_configured"
