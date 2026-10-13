from __future__ import annotations


def test_providers_default_statuses(client):
    body = client.get("/api/providers").json()
    by_id = {p["id"]: p for p in body["providers"]}
    assert by_id["aws"]["status"] == "disabled"
    assert by_id["docker"]["status"] == "disabled"
    assert by_id["azure"]["status"] == "disabled"
    assert by_id["demo"]["status"] == "demo"
    assert body["mode"] == "demo"


def test_providers_never_expose_secrets(client):
    raw = client.get("/api/providers").text.lower()
    for leaked in ("secret", "api_key", "password", "token"):
        assert leaked not in raw


def test_aws_reports_unconfigured_without_credentials(make_client):
    client = make_client(AWS_ENABLED="true", AWS_DEFAULT_REGION="us-east-1")
    body = client.get("/api/providers").json()
    aws = next(p for p in body["providers"] if p["id"] == "aws")
    assert aws["status"] in {"unconfigured", "error"}
    assert aws["setup_hint"]


def test_azure_stays_honest_when_enabled(make_client):
    client = make_client(AZURE_ENABLED="true")
    body = client.get("/api/providers").json()
    azure = next(p for p in body["providers"] if p["id"] == "azure")
    assert azure["status"] == "unconfigured"
    assert azure["capabilities"] == []
