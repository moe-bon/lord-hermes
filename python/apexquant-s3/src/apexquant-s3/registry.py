from __future__ import annotations

from apexquant_s3.models import BucketPurpose, BucketSpec


class BucketRegistry:
    def __init__(self, environment: str) -> None:
        self._environment = environment
        self._specs = self._build_specs()

    def _prefix(self, name: str) -> str:
        return f"{self._environment}-{name}"

    def _build_specs(self) -> list[BucketSpec]:
        return [
            BucketSpec(
                name=self._prefix("apex-market-data-raw"),
                purpose=BucketPurpose.MARKET_DATA_RAW,
                versioning_enabled=False,
                lifecycle_expiration_days=365,
            ),
            BucketSpec(
                name=self._prefix("apex-models"),
                purpose=BucketPurpose.MODEL_ARTIFACTS,
                versioning_enabled=True,
            ),
            BucketSpec(
                name=self._prefix("apex-knowledge-raw"),
                purpose=BucketPurpose.KNOWLEDGE_RAW,
                versioning_enabled=True,
            ),
            BucketSpec(
                name=self._prefix("apex-backups"),
                purpose=BucketPurpose.BACKUPS,
                versioning_enabled=False,
                lifecycle_expiration_days=90,
            ),
            BucketSpec(
                name=self._prefix("apex-temp"),
                purpose=BucketPurpose.TEMPORARY,
                versioning_enabled=False,
                lifecycle_expiration_days=7,
            ),
        ]

    def specs(self) -> list[BucketSpec]:
        return self._specs

    def get(self, purpose: BucketPurpose) -> BucketSpec:
        for spec in self._specs:
            if spec.purpose == purpose:
                return spec
        raise KeyError(f"no bucket registered for purpose {purpose.value}")