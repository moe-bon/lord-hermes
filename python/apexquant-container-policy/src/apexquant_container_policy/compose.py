from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ComposeHealthcheck(BaseModel):
    test: str | list[str] | None = None
    interval: str | None = None
    timeout: str | None = None
    retries: int | None = None
    start_period: str | None = None


class ComposeService(BaseModel):
    name: str
    image: str | None = None
    build: dict[str, Any] | str | None = None
    user: str | None = None
    read_only: bool = False
    privileged: bool = False
    security_opt: list[str] = Field(default_factory=list)
    cap_drop: list[str] = Field(default_factory=list)
    healthcheck: ComposeHealthcheck | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    networks: set[str] = Field(default_factory=set)
    labels: dict[str, str] = Field(default_factory=dict)
    deploy: dict[str, Any] | None = None


class ComposeDocument(BaseModel):
    services: dict[str, ComposeService]
    networks: set[str] = Field(default_factory=set)
    volumes: set[str] = Field(default_factory=set)


def load_compose(path: Path) -> ComposeDocument:
    raw_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)

    if not isinstance(raw, dict):
        raise ValueError("compose file must contain a YAML mapping")

    services_raw = raw.get("services")

    if not isinstance(services_raw, dict):
        raise ValueError("compose file must define a services mapping")

    services: dict[str, ComposeService] = {}

    for service_name, service_raw in services_raw.items():
        services[str(service_name)] = _parse_service(
            str(service_name),
            service_raw if isinstance(service_raw, dict) else {},
        )

    networks_raw = raw.get("networks")
    volumes_raw = raw.get("volumes")

    networks: set[str] = set()
    volumes: set[str] = set()

    if isinstance(networks_raw, dict):
        networks = {str(name) for name in networks_raw.keys()}

    if isinstance(volumes_raw, dict):
        volumes = {str(name) for name in volumes_raw.keys()}

    return ComposeDocument(
        services=services,
        networks=networks,
        volumes=volumes,
    )


def _parse_service(name: str, raw: dict[str, Any]) -> ComposeService:
    healthcheck_raw = raw.get("healthcheck")
    healthcheck: ComposeHealthcheck | None = None

    if isinstance(healthcheck_raw, dict):
        healthcheck = ComposeHealthcheck(
            test=healthcheck_raw.get("test"),
            interval=_optional_str(healthcheck_raw.get("interval")),
            timeout=_optional_str(healthcheck_raw.get("timeout")),
            retries=_optional_int(healthcheck_raw.get("retries")),
            start_period=_optional_str(healthcheck_raw.get("start_period")),
        )

    deploy_raw = raw.get("deploy")
    deploy: dict[str, Any] | None = None

    if isinstance(deploy_raw, dict):
        deploy = deploy_raw

    build_raw = raw.get("build")
    build: dict[str, Any] | str | None = None

    if isinstance(build_raw, str):
        build = build_raw
    elif isinstance(build_raw, dict):
        build = build_raw

    return ComposeService(
        name=name,
        image=_optional_str(raw.get("image")),
        build=build,
        user=_optional_str(raw.get("user")),
        read_only=bool(raw.get("read_only", False)),
        privileged=bool(raw.get("privileged", False)),
        security_opt=_parse_string_list(raw.get("security_opt")),
        cap_drop=_parse_string_list(raw.get("cap_drop")),
        healthcheck=healthcheck,
        environment=_parse_environment(raw.get("environment")),
        networks=_parse_networks(raw.get("networks")),
        labels=_parse_labels(raw.get("labels")),
        deploy=deploy,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    return int(value)


def _parse_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, str):
        return [raw]

    if isinstance(raw, list):
        return [str(item) for item in raw]

    return []


def _parse_environment(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}

    if isinstance(raw, dict):
        parsed: dict[str, str] = {}

        for key, value in raw.items():
            if value is None:
                parsed[str(key)] = ""
            else:
                parsed[str(key)] = str(value)

        return parsed

    if isinstance(raw, list):
        parsed = {}

        for item in raw:
            item_str = str(item)

            if "=" in item_str:
                key, value = item_str.split("=", 1)
                parsed[key.strip()] = value.strip()
            else:
                parsed[item_str.strip()] = ""

        return parsed

    return {}


def _parse_networks(raw: Any) -> set[str]:
    if raw is None:
        return set()

    if isinstance(raw, str):
        return {raw}

    if isinstance(raw, list):
        return {str(item) for item in raw}

    if isinstance(raw, dict):
        return {str(key) for key in raw.keys()}

    return set()


def _parse_labels(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}

    if isinstance(raw, dict):
        parsed: dict[str, str] = {}

        for key, value in raw.items():
            if isinstance(value, bool):
                parsed[str(key)] = "true" if value else "false"
            elif value is None:
                parsed[str(key)] = ""
            else:
                parsed[str(key)] = str(value)

        return parsed

    if isinstance(raw, list):
        parsed = {}

        for item in raw:
            item_str = str(item)

            if "=" in item_str:
                key, value = item_str.split("=", 1)
                parsed[key.strip()] = value.strip()
            else:
                parsed[item_str.strip()] = ""

        return parsed

    return {}