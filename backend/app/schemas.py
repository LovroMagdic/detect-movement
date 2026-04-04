from typing import Any

from pydantic import BaseModel


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str | None = None
    stage_detail: str | None = None
    progress: float | None = None
    error: str | None = None
    steps: list[dict[str, str]] | None = None
    artifacts: dict[str, str] | None = None
    meta: dict[str, Any] | None = None

