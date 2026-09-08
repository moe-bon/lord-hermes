from __future__ import annotations

import json

import httpx

from apexquant_logging.models import LogEnvelope


async def insert_logs_into_clickhouse(
    clickhouse_url: str,
    database: str,
    logs: list[LogEnvelope],
) -> None:
    lines: list[str] = []

    for log in logs:
        payload = log.model_dump(mode="json")
        payload["data"] = json.dumps(payload.get("data", {}), default=str)

        lines.append(json.dumps(payload, default=str))

    body = "\n".join(lines)

    url = f"{clickhouse_url.rstrip('/')}/?database={database}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            url,
            params={"query": "INSERT INTO structured_logs FORMAT JSONEachRow"},
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

        response.raise_for_status()