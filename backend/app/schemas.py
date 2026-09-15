from datetime import datetime
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


class JobListItem(BaseModel):
    job_id: str
    filename: str
    status: str
    updated_at: datetime


class JobSummary(BaseModel):
    job_id: str
    filename: str
    created_at: datetime
    updated_at: datetime
    artifacts: list[str]
    has_results: bool
    frame_count: int = 0
    status: str


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    total: int
