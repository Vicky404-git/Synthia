"""AWS adapter tests using mocks (no real cloud calls)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import ProviderError
from app.providers.aws_provider import AWSProvider


class _FakePaginator:
    def paginate(self):
        return [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-abc123",
                                "InstanceType": "t3.micro",
                                "State": {"Name": "running"},
                                "Placement": {"AvailabilityZone": "us-east-1a"},
                                "PrivateIpAddress": "10.0.0.5",
                                "Tags": [{"Key": "Name", "Value": "demo-web"}],
                            }
                        ]
                    }
                ]
            }
        ]


class _FakeEC2:
    def get_paginator(self, name):
        assert name == "describe_instances"
        return _FakePaginator()

    def describe_instances(self, InstanceIds):
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": InstanceIds[0],
                            "InstanceType": "t3.micro",
                            "State": {"Name": "stopped"},
                            "Placement": {"AvailabilityZone": "us-east-1b"},
                            "Tags": [{"Key": "Env", "Value": "test"}],
                        }
                    ]
                }
            ]
        }


class _FakeS3:
    def list_buckets(self):
        return {"Buckets": [{"Name": "bucket-a", "CreationDate": "2024-01-01"}]}


@pytest.fixture
def provider():
    settings = Settings(aws_enabled=True, aws_default_region="us-east-1")
    instance = AWSProvider(settings)
    instance._client = lambda service, region=None: (  # type: ignore[assignment]
        _FakeEC2() if service == "ec2" else _FakeS3()
    )
    return instance


def test_list_ec2_instances(provider):
    result = provider.list_ec2_instances()
    assert result.simulated is False
    assert result.data["count"] == 1
    assert result.data["instances"][0]["id"] == "i-abc123"
    assert result.data["instances"][0]["name"] == "demo-web"


def test_describe_instance(provider):
    result = provider.describe_instance("i-xyz")
    assert result.data["id"] == "i-xyz"
    assert result.data["state"] == "stopped"


def test_list_s3_buckets(provider):
    result = provider.list_s3_buckets()
    assert result.data["buckets"][0]["name"] == "bucket-a"


def test_aws_disabled_raises():
    provider = AWSProvider(Settings(aws_enabled=False))
    with pytest.raises(Exception) as exc:
        provider.list_ec2_instances()
    assert "disabled" in str(exc.value).lower()


def test_aws_error_is_mapped():
    provider = AWSProvider(Settings(aws_enabled=True, aws_default_region="us-east-1"))

    class _Boom:
        def get_paginator(self, name):
            raise RuntimeError("network down")

    provider._client = lambda service, region=None: _Boom()  # type: ignore[assignment]
    with pytest.raises(ProviderError):
        provider.list_ec2_instances()


def test_health_reports_unconfigured_without_credentials():
    provider = AWSProvider(Settings(aws_enabled=True, aws_default_region="us-east-1"))
    health = provider.health()
    assert health.status.value in {"unconfigured", "error"}
