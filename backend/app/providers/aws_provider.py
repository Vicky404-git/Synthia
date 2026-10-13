"""AWS adapter (read-only).

Uses boto3's normal credential chain (IAM role, shared config, or environment
variables). It is deliberately read-only in V1: it lists and describes
resources, and never mutates anything.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..errors import ProviderError, ProviderNotConfiguredError
from ..schemas import ProviderStatus
from .base import CloudProvider, ProviderHealth, ProviderResult


class AWSProvider(CloudProvider):
    id = "aws"
    label = "AWS"
    read_only = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- health ------------------------------------------------------------

    def _credentials_available(self) -> tuple[bool, str]:
        try:
            import boto3  # noqa: PLC0415
        except ImportError:
            return False, "boto3 is not installed."
        try:
            session = boto3.Session()
            credentials = session.get_credentials()
        except Exception:  # pragma: no cover - defensive
            return False, "Could not initialise a boto3 session."
        if credentials is None:
            return False, "No AWS credentials found in the environment or chain."
        method = getattr(credentials, "method", "unknown")
        return True, f"Credentials resolved via {method}."

    def health(self) -> ProviderHealth:
        if not self._settings.aws_enabled:
            return ProviderHealth(
                status=ProviderStatus.disabled,
                detail="AWS integration is disabled (set AWS_ENABLED=true).",
                capabilities=self.capabilities(),
                setup_hint="Set AWS_ENABLED=true and AWS_DEFAULT_REGION.",
            )
        if not self._settings.aws_default_region:
            return ProviderHealth(
                status=ProviderStatus.unconfigured,
                detail="AWS_DEFAULT_REGION is not set.",
                capabilities=self.capabilities(),
                setup_hint="Set AWS_DEFAULT_REGION to a region you can read.",
            )
        available, detail = self._credentials_available()
        if not available:
            return ProviderHealth(
                status=ProviderStatus.unconfigured,
                detail=detail,
                capabilities=self.capabilities(),
                setup_hint=(
                    "Provide AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, or run "
                    "on a role with read-only permissions."
                ),
            )
        return ProviderHealth(
            status=ProviderStatus.connected,
            detail=f"{detail} Read-only operations are available.",
            capabilities=self.capabilities(),
        )

    def capabilities(self) -> list[str]:
        return ["List EC2 instances", "Describe an EC2 instance", "List S3 buckets"]

    # -- helpers -----------------------------------------------------------

    def _client(self, service: str, region: str | None = None) -> Any:
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderNotConfiguredError(
                "boto3 is required for the AWS integration.",
                details={"provider": self.id},
            ) from exc
        if not self._settings.aws_enabled:
            raise ProviderNotConfiguredError(
                "AWS integration is disabled.",
                details={"provider": self.id, "hint": "set AWS_ENABLED=true"},
            )
        kwargs: dict[str, Any] = {
            "region_name": region or self._settings.aws_default_region,
        }
        # boto3 also reads these from the environment; passing explicitly keeps
        # behaviour predictable when running in a container.
        if self._settings.aws_access_key_id:
            kwargs["aws_access_key_id"] = self._settings.aws_access_key_id
        if self._settings.aws_secret_access_key:
            kwargs["aws_secret_access_key"] = self._settings.aws_secret_access_key
        if self._settings.aws_session_token:
            kwargs["aws_session_token"] = self._settings.aws_session_token
        return boto3.client(service, **kwargs)

    @staticmethod
    def _map_error(exc: Exception, what: str) -> ProviderError:
        code = "unknown"
        try:
            from botocore.exceptions import ClientError  # noqa: PLC0415

            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code", "ClientError")
        except ImportError:  # pragma: no cover
            pass
        friendly = {
            "AccessDenied": "Access denied. The IAM policy does not allow this.",
            "AccessDeniedException": "Access denied for this operation.",
            "UnauthorizedOperation": "This credential cannot perform the request.",
            "InvalidClientTokenId": "The AWS credential is invalid.",
            "ExpiredToken": "The AWS session token has expired.",
        }.get(code, f"AWS returned an error while trying to {what}.")
        return ProviderError(friendly, details={"provider": "aws", "aws_code": code})

    # -- operations --------------------------------------------------------

    def list_ec2_instances(self, region: str | None = None) -> ProviderResult:
        client = self._client("ec2", region)
        try:
            paginator = client.get_paginator("describe_instances")
            instances: list[dict[str, Any]] = []
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        state = instance.get("State", {})
                        name = ""
                        for tag in instance.get("Tags", []) or []:
                            if tag.get("Key") == "Name":
                                name = tag.get("Value", "")
                        instances.append(
                            {
                                "id": instance.get("InstanceId"),
                                "name": name,
                                "type": instance.get("InstanceType"),
                                "state": state.get("Name"),
                                "az": instance.get("Placement", {}).get("AvailabilityZone"),
                                "private_ip": instance.get("PrivateIpAddress"),
                                "public_ip": instance.get("PublicIpAddress"),
                            }
                        )
        except Exception as exc:
            raise self._map_error(exc, "list EC2 instances") from exc
        return ProviderResult(
            data={
                "region": region or self._settings.aws_default_region,
                "count": len(instances),
                "instances": instances,
            },
            provider=self.id,
            message=f"Found {len(instances)} EC2 instance(s).",
        )

    def describe_instance(
        self, instance_id: str, region: str | None = None
    ) -> ProviderResult:
        client = self._client("ec2", region)
        try:
            response = client.describe_instances(InstanceIds=[instance_id])
        except Exception as exc:
            raise self._map_error(exc, f"describe instance {instance_id}") from exc
        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise ProviderError(
                "No instance found with that ID.",
                details={"provider": self.id},
                status_code=404,
            )
        instance = reservations[0]["Instances"][0]
        return ProviderResult(
            data={
                "id": instance.get("InstanceId"),
                "type": instance.get("InstanceType"),
                "state": instance.get("State", {}).get("Name"),
                "az": instance.get("Placement", {}).get("AvailabilityZone"),
                "private_ip": instance.get("PrivateIpAddress"),
                "public_ip": instance.get("PublicIpAddress"),
                "launch_time": str(instance.get("LaunchTime", "")),
                "tags": {
                    tag.get("Key"): tag.get("Value")
                    for tag in instance.get("Tags", []) or []
                },
            },
            provider=self.id,
            message=f"Instance {instance_id} described.",
        )

    def list_s3_buckets(self) -> ProviderResult:
        client = self._client("s3")
        try:
            response = client.list_buckets()
        except Exception as exc:
            raise self._map_error(exc, "list S3 buckets") from exc
        buckets = [
            {"name": item.get("Name"), "creation_date": str(item.get("CreationDate", ""))}
            for item in response.get("Buckets", [])
        ]
        return ProviderResult(
            data={"count": len(buckets), "buckets": buckets},
            provider=self.id,
            message=f"Found {len(buckets)} S3 bucket(s).",
        )
