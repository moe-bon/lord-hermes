from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class ApiInfo(BaseModel):
    service_name: str
    service_version: str
    environment: str
    plane: str
    api_version: str = "v1"
    description: str = Field(default="")