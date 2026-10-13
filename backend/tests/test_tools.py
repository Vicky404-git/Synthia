from __future__ import annotations


def test_tools_catalogue(client):
    body = client.get("/api/tools").json()
    names = {t["name"] for t in body["tools"]}
    assert "demo.list_ec2_instances" in names
    assert "aws.list_ec2_instances" in names
    assert "docker.list_containers" in names
    assert body["count"] == len(body["tools"])


def test_aws_tool_reports_unavailable_reason(client):
    body = client.get("/api/tools").json()
    aws_tool = next(t for t in body["tools"] if t["name"] == "aws.list_ec2_instances")
    assert aws_tool["available"] is False
    assert aws_tool["unavailable_reason"]


def test_tool_has_json_schema(client):
    body = client.get("/api/tools").json()
    tool = next(t for t in body["tools"] if t["name"] == "aws.describe_instance")
    assert tool["parameters"]["type"] == "object"
    assert "instance_id" in tool["parameters"]["properties"]
    assert tool["read_only"] is True
