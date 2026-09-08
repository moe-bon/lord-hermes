"""Cross-language bucketing. Conforms EXACTLY to the shared fixture.

The Rust crate embeds the same file via include_str!; CI asserts both sides
match and produce identical verdicts on the shared conformance vectors.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import xxhash
import yaml

SEED = 0x9E3779B97F4A7C15
MODULUS = 10_000


class DeterminismSpec:
    def __init__(self, raw: dict) -> None:
        self.version = int(raw["version"])
        self.algorithm = raw["hash"]["algorithm"]
        self.seed = int(str(raw["hash"]["seed"]), 16)
        self.modulus = int(raw["bucketing"]["modulus"])
        self.entity_priority: list[str] = list(raw["bucketing"]["entity_priority"])

        # Drift tripwires — must match the compiled-in Rust constants.
        if self.algorithm != "xxhash64":
            raise ValueError("determinism fixture hash algorithm drifted")
        if self.seed != SEED:
            raise ValueError("determinism fixture seed drifted")
        if self.modulus != MODULUS:
            raise ValueError("determinism fixture modulus drifted")

    @classmethod
    def load(cls) -> DeterminismSpec:
        # Prefer the packaged fixture; fall back to the repo path.
        try:
            ref = resources.files("apexquant_flags").joinpath("data/determinism.yaml")
            text = ref.read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            repo_path = Path(__file__).resolve().parents[4] / (
                "data/feature_flags/determinism.yaml"
            )
            text = repo_path.read_text(encoding="utf-8")

        return cls(yaml.safe_load(text))


def select_bucketing_entity(
    attributes: list[tuple[str, str]],
    priority: list[str],
) -> str | None:
    """First present attribute in priority order; None if absent."""
    lookup = {}
    for key, value in attributes:
        if key not in lookup and value:
            lookup[key] = value

    for wanted in priority:
        if wanted in lookup and lookup[wanted]:
            return lookup[wanted]
    return None


def bucket_for(flag_key: str, entity: str) -> int:
    """xxhash64(utf8(f'{flag_key}:{entity}'), seed) mod 10_000."""
    payload = f"{flag_key}:{entity}".encode("utf-8")
    return xxhash.xxh64(payload, seed=SEED).intdigest() % MODULUS