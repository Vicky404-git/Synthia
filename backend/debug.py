#!/usr/bin/env python3
"""Synthia environment & integration doctor.

Checks that every environment variable and optional integration is wired up
correctly. By default it performs only *local* checks (no network calls). Pass
``--live`` to additionally attempt real connectivity to the configured LLM,
AWS, and Docker integrations.

Usage:
    python debug.py                 # safe local checks
    python debug.py --live          # also ping real services
    python debug.py --json          # machine-readable output

Exit code is 0 when everything required is OK, 1 if any check FAILed.
Secrets are always masked; nothing sensitive is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Resolve paths from this script, not from the shell's current directory.
# Supports both: repo-root/debug.py and repo-root/backend/debug.py.
SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR / "app").is_dir():
    BACKEND_DIR = SCRIPT_DIR
elif (SCRIPT_DIR / "backend" / "app").is_dir():
    BACKEND_DIR = SCRIPT_DIR / "backend"
else:
    BACKEND_DIR = SCRIPT_DIR

REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
ENV_PATHS = [REPO_ROOT / ".env", BACKEND_DIR / ".env"]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_project_env() -> str | None:
    """Load the repo-root .env without overriding variables already exported."""
    env_path = next((path for path in ENV_PATHS if path.is_file()), None)
    if env_path is None:
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        # Minimal fallback for simple KEY=value .env files. Preserve shell env.
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and key.replace("_", "").isalnum():
                    os.environ.setdefault(key, value)
        except OSError as exc:
            return f"Found .env but could not read it ({type(exc).__name__})"
    return str(env_path)


ENV_LOAD_RESULT = load_project_env()

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

_LEVEL_ICON = {OK: "✓", WARN: "!", FAIL: "✗", SKIP: "·"}
_LEVEL_COLOR = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m", SKIP: "\033[90m"}
_RESET = "\033[0m"


@dataclass
class Check:
    name: str
    level: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, level: str, detail: str = "") -> None:
        self.checks.append(Check(name, level, detail))

    @property
    def failed(self) -> bool:
        return any(check.level == FAIL for check in self.checks)

    def counts(self) -> dict[str, int]:
        counts = {OK: 0, WARN: 0, FAIL: 0, SKIP: 0}
        for check in self.checks:
            counts[check.level] = counts.get(check.level, 0) + 1
        return counts


def mask(value: str | None) -> str:
    """Show only enough of a secret to confirm it is set."""
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "set (short)"
    return f"{value[:4]}…{value[-4:]} (len {len(value)})"


def banner(title: str) -> None:
    print(f"\n\033[36m── {title} " + "─" * max(0, 58 - len(title)) + _RESET)


# --- Checks -----------------------------------------------------------------


def check_python(report: Report) -> None:
    report.add(
        "python",
        OK if sys.version_info >= (3, 11) else FAIL,
        f"{sys.version.split()[0]} (requires >=3.11)",
    )


def check_packages(report: Report) -> None:
    required = ["fastapi", "uvicorn", "pydantic", "pydantic_settings", "httpx"]
    optional = ["boto3", "docker", "multipart"]
    for module in required:
        try:
            importlib.import_module(module)
            report.add(f"package:{module}", OK, "installed")
        except ImportError:
            report.add(f"package:{module}", FAIL, "missing (required)")
    for module in optional:
        try:
            importlib.import_module(module)
            report.add(f"package:{module}", OK, "installed")
        except ImportError:
            report.add(f"package:{module}", WARN, "missing (needed for that provider)")


def check_env_file(report: Report) -> None:
    env_path = next((path for path in ENV_PATHS if path.is_file()), None)
    if env_path is None:
        report.add(".env file", WARN, f"not found in: {', '.join(map(str, ENV_PATHS))}")
    elif ENV_LOAD_RESULT and ENV_LOAD_RESULT.startswith("Found .env"):
        report.add(".env file", WARN, f"{env_path} — {ENV_LOAD_RESULT}")
    else:
        report.add(".env file", OK, f"loaded {env_path} (existing shell variables take precedence)")


def check_settings(report: Report) -> "object | None":
    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        report.add("settings load", FAIL, f"{type(exc).__name__}: {exc}")
        return None
    report.add("settings load", OK, "pydantic Settings parsed successfully")

    report.add("APP_ENV", OK, settings.app_env)
    report.add("PORT", OK, str(settings.port))
    report.add(
        "DEMO_MODE",
        OK,
        "true (no paid credentials required)" if settings.demo_mode else "false",
    )
    report.add(
        "CORS_ALLOWED_ORIGINS",
        OK if settings.cors_allowed_origins else WARN,
        ", ".join(settings.cors_allowed_origins) or "(none)",
    )
    report.add(
        "API_AUTH_TOKEN",
        OK if settings.api_auth_token else WARN,
        mask(settings.api_auth_token),
    )
    report.add(
        "ALLOW_MUTATING",
        OK,
        "true (mutating tools gated by confirmation)"
        if settings.allow_mutating
        else "false (read-only, safe default)",
    )
    report.add("RATE_LIMIT_PER_MINUTE", OK, str(settings.rate_limit_per_minute))

    # LLM
    if settings.llm_provider == "demo":
        report.add("LLM", WARN, "provider=demo (offline; no real answers)")
    elif settings.llm_configured:
        report.add(
            "LLM",
            OK,
            f"provider={settings.llm_provider} model={settings.llm_model} "
            f"key={mask(settings.llm_api_key)}",
        )
    else:
        report.add(
            "LLM",
            FAIL,
            f"provider={settings.llm_provider} but LLM_API_KEY is not set",
        )
    report.add("LLM_BASE_URL", OK, settings.llm_base_url)

    # STT
    if settings.stt_provider == "none":
        report.add("STT", WARN, "none (browser Web Speech API / typed input only)")
    elif settings.stt_configured:
        report.add(
            "STT",
            OK,
            f"provider={settings.stt_provider} model={settings.stt_model} "
            f"key={mask(settings.stt_api_key)}",
        )
    else:
        report.add(
            "STT", FAIL, f"provider={settings.stt_provider} but STT_API_KEY is not set"
        )

    # AWS
    report.add(
        "AWS_ENABLED",
        OK if settings.aws_enabled else WARN,
        "true" if settings.aws_enabled else "false",
    )
    report.add("AWS_DEFAULT_REGION", OK, settings.aws_default_region)
    if settings.aws_enabled:
        has_env_keys = bool(settings.aws_access_key_id and settings.aws_secret_access_key)
        report.add(
            "AWS credentials (env)",
            OK if has_env_keys else WARN,
            "set in environment"
            if has_env_keys
            else "not in env — relying on the AWS credential chain",
        )

    # Docker
    report.add(
        "DOCKER_ENABLED",
        OK if settings.docker_enabled else WARN,
        "true" if settings.docker_enabled else "false",
    )
    report.add("DOCKER_SOCKET", OK, settings.docker_socket)
    if settings.docker_enabled and settings.is_production:
        report.add(
            "Docker/production",
            WARN,
            "Docker is force-disabled in production for safety",
        )

    # Azure
    report.add(
        "AZURE_ENABLED",
        WARN if settings.azure_enabled else OK,
        "enabled but no live adapter is implemented (interface only)"
        if settings.azure_enabled
        else "false (interface only — not implemented)",
    )
    return settings


def check_providers(report: Report) -> None:
    try:
        from app.providers import get_provider_registry
        from app.tools import get_tool_registry

        registry = get_provider_registry()
        for provider_id, health in registry.all_health():
            level = OK if health.status.value in {"connected", "demo"} else WARN
            report.add(f"provider:{provider_id}", level, f"{health.status.value} — {health.detail}")

        tools = get_tool_registry().all()
        available = [tool for tool in tools if tool.available]
        report.add(
            "tools",
            OK if available else WARN,
            f"{len(available)}/{len(tools)} available",
        )
        for tool in tools:
            report.add(
                f"tool:{tool.name}",
                OK if tool.available else SKIP,
                "available" if tool.available else (tool.unavailable_reason() or "unavailable"),
            )
    except Exception as exc:  # noqa: BLE001
        report.add("providers/tools", FAIL, f"{type(exc).__name__}: {exc}")


async def check_llm_live(report: Report, settings) -> None:
    if not settings.llm_configured:
        report.add("LLM live", SKIP, "no live LLM configured")
        return
    try:
        from app.llm import get_llm_provider

        provider = get_llm_provider()
        result = await provider.complete(
            [{"role": "user", "content": "Reply with the single word: pong"}],
            max_tokens=10,
        )
        reply = result.text.strip().replace("\n", " ")[:60]
        report.add("LLM live", OK, f"model={result.model} replied: {reply!r}")
    except Exception as exc:  # noqa: BLE001
        report.add("LLM live", FAIL, f"{type(exc).__name__}: {exc}")


def check_aws_live(report: Report, settings) -> None:
    if not settings.aws_enabled:
        report.add("AWS live", SKIP, "AWS_ENABLED=false")
        return

    try:
        import boto3

        # Use credentials loaded by app settings when present; otherwise let
        # boto3 use its normal profile/role credential chain.
        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            region_name=settings.aws_default_region,
        )
    except Exception as exc:  # noqa: BLE001
        report.add("AWS session", FAIL, f"{type(exc).__name__}: {_short(exc)}")
        return

    try:
        identity = session.client("sts", region_name=settings.aws_default_region).get_caller_identity()
        report.add("AWS identity", OK, f"credentials valid; account={identity.get('Account')}")
    except Exception as exc:  # noqa: BLE001
        report.add("AWS identity", FAIL, f"{type(exc).__name__}: {_short(exc)}")
        # Without valid credentials, the following checks are unlikely to help.
        return

    try:
        ec2 = session.client("ec2", region_name=settings.aws_default_region)
        response = ec2.describe_instances(MaxResults=5)
        count = sum(len(r.get("Instances", [])) for r in response.get("Reservations", []))
        report.add("AWS EC2 read", OK, f"DescribeInstances OK (sample {count} instance(s))")
    except Exception as exc:  # noqa: BLE001
        report.add("AWS EC2 read", FAIL, f"{type(exc).__name__}: {_short(exc)}")

    try:
        s3 = session.client("s3", region_name=settings.aws_default_region)
        buckets = s3.list_buckets().get("Buckets", [])
        report.add("AWS S3 read", OK, f"ListBuckets OK ({len(buckets)} bucket(s) visible)")
    except Exception as exc:  # noqa: BLE001
        report.add("AWS S3 read", FAIL, f"{type(exc).__name__}: {_short(exc)}")


def check_docker_live(report: Report, settings) -> None:
    if not settings.docker_enabled:
        report.add("Docker live", SKIP, "DOCKER_ENABLED=false")
        return
    if settings.is_production:
        report.add("Docker live", SKIP, "disabled in production")
        return
    try:
        import docker

        client = docker.DockerClient(base_url=settings.docker_socket, timeout=5)
        client.ping()
        containers = client.containers.list(all=True)
        report.add("Docker live", OK, f"daemon reachable, {len(containers)} container(s)")
    except ImportError:
        report.add("Docker live", FAIL, "docker SDK not installed")
    except Exception as exc:  # noqa: BLE001
        report.add("Docker live", FAIL, f"{type(exc).__name__}: {_short(exc)}")


def _short(exc: Exception, limit: int = 140) -> str:
    text = str(exc).replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def check_app_apploads(report: Report) -> None:
    try:
        from app.main import app

        routes = [getattr(route, "path", "") for route in app.routes]
        report.add("app import", OK, f"FastAPI app loaded ({len(routes)} routes)")
    except Exception as exc:  # noqa: BLE001
        report.add("app import", FAIL, f"{type(exc).__name__}: {exc}")


# --- Main -------------------------------------------------------------------


def run(live: bool, *, quiet: bool = False) -> Report:
    report = Report()
    if not quiet:
        print("\033[1mSynthia environment doctor\033[0m")

    if not quiet:
        banner("RUNTIME")
    check_python(report)
    check_packages(report)

    if not quiet:
        banner("CONFIGURATION")
    check_env_file(report)
    settings = check_settings(report)

    if not quiet:
        banner("INTEGRATIONS (local)")
    check_providers(report)
    check_app_apploads(report)

    if live and settings is not None:
        if not quiet:
            banner("INTEGRATIONS (live)")
        asyncio.run(check_llm_live(report, settings))
        check_aws_live(report, settings)
        check_docker_live(report, settings)

    return report


def print_report(report: Report) -> None:
    color = sys.stdout.isatty()
    for check in report.checks:
        icon = _LEVEL_ICON.get(check.level, "?")
        if color:
            prefix = f"{_LEVEL_COLOR.get(check.level, '')}{check.level:<4}{_RESET}"
        else:
            prefix = f"{check.level:<4}"
        name = check.name[:34].ljust(34)
        print(f"  {prefix} {icon} {name} {check.detail}")
    counts = report.counts()
    print(
        f"\n  summary: {counts[OK]} ok, {counts[WARN]} warn, "
        f"{counts[FAIL]} fail, {counts[SKIP]} skipped"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthia environment doctor")
    parser.add_argument(
        "--live",
        action="store_true",
        help="attempt real connectivity to LLM/AWS/Docker",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    report = run(live=args.live, quiet=args.json)

    if args.json:
        print(
            json.dumps(
                {
                    "checks": [check.__dict__ for check in report.checks],
                    "counts": report.counts(),
                    "failed": report.failed,
                },
                indent=2,
            )
        )
    else:
        banner("RESULT")
        print_report(report)
        if report.failed:
            print("\n\033[31mOne or more checks FAILED.\033[0m")
        else:
            print("\n\033[32mAll required checks passed.\033[0m")

    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
