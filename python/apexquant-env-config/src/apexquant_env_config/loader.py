from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from apexquant_env_config.models import EnvironmentManifest

ENV_VAR_REFERENCE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_manifest(path: Path) -> EnvironmentManifest:
    raw_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)

    if not isinstance(raw, dict):
        raise ValueError("environment manifest must be a YAML mapping")

    return EnvironmentManifest.model_validate(raw)


def extract_required_env_vars(manifest: EnvironmentManifest) -> list[str]:
    payload = json.dumps(manifest.model_dump(mode="json"))
    matches = ENV_VAR_REFERENCE_PATTERN.findall(payload)

    return sorted(set(matches))