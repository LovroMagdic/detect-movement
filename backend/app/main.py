import os
import re
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from rq.job import Job

from app.queue import get_queue, get_redis
from app.schemas import CreateJobResponse, JobListItem, JobListResponse, JobStatusResponse, JobSummary
from app.storage import (
    delete_job_assets,
    ensure_storage_ready,
    get_asset_by_api_name,
    get_job_summary,
    job_exists,
    list_api_artifacts,
    list_jobs,
    save_job_meta,
    save_upload_file,
)
from app.tasks import process_video_job_task


UPLOAD_CHUNK_SIZE = 1024 * 1024
ARTIFACT_NAMES = {"map", "heatmap", "overlay", "csv", "metadata", "forest_overlay"}

app = FastAPI(title="Detect Motion API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    ensure_storage_ready()


def _rq_status_str(job: Job) -> str:
    st = job.get_status(refresh=True)
    if hasattr(st, "value"):
        return str(st.value)
    return str(st)


def _artifact_urls(job_id: str, artifact_keys: list[str]) -> dict[str, str]:
    return {k: f"/api/jobs/{job_id}/artifacts/{k}" for k in artifact_keys}


def _resolve_artifact_keys(job: Job) -> list[str] | None:
    result = job.result if isinstance(job.result, dict) else None
    if result and isinstance(result.get("artifacts"), list):
        return result["artifacts"]
    if result and isinstance(result.get("artifacts"), dict):
        return list(result["artifacts"].keys())
    status = _rq_status_str(job).lower()
    if status == "finished":
        keys = list_api_artifacts(job.id)
        return keys or None
    return None


def _job_response(job: Job) -> JobStatusResponse:
    status = _rq_status_str(job)
    artifact_keys = _resolve_artifact_keys(job)
    artifacts = _artifact_urls(job.id, artifact_keys) if artifact_keys else None
    return JobStatusResponse(
        job_id=job.id,
        status=status,
        stage=job.meta.get("stage"),
        stage_detail=job.meta.get("stage_detail"),
        progress=job.meta.get("progress"),
        error=job.meta.get("error"),
        steps=job.meta.get("steps"),
        artifacts=artifacts,
        meta=dict(job.meta),
    )


def _db_job_response(job_id: str) -> JobStatusResponse:
    summary = get_job_summary(job_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    artifact_keys = summary.artifacts
    artifacts = _artifact_urls(job_id, artifact_keys) if artifact_keys else None
    progress = 1.0 if summary.status == "finished" else None
    return JobStatusResponse(
        job_id=job_id,
        status=summary.status,
        stage="archived" if summary.status == "finished" else "stored",
        stage_detail="Archived job loaded from database.",
        progress=progress,
        error=None,
        steps=None,
        artifacts=artifacts,
        meta={"filename": summary.filename, "frame_count": summary.frame_count},
    )


def _list_item_to_schema(item) -> JobListItem:
    return JobListItem(
        job_id=item.job_id,
        filename=item.filename,
        status=item.status,
        updated_at=item.updated_at,
    )


def _summary_to_schema(summary) -> JobSummary:
    return JobSummary(
        job_id=summary.job_id,
        filename=summary.filename,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        artifacts=summary.artifacts,
        has_results=summary.has_results,
        frame_count=summary.frame_count,
        status=summary.status,
    )


def _safe_filename(name: str | None) -> str:
    if not name:
        return "upload.bin"
    base = os.path.basename(name)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    return safe or "upload.bin"


def _upload_content_type(filename: str, provided: str | None) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".mp4", ".m4v"}:
        return "video/mp4"
    if ext == ".mkv":
        return "video/x-matroska"
    if ext == ".webm":
        return "video/webm"
    if ext == ".avi":
        return "video/x-msvideo"
    if ext == ".mov":
        return "video/quicktime"
    return "application/octet-stream"


async def _read_upload_bytes(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
    await file.close()
    return b"".join(chunks)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/jobs", response_model=CreateJobResponse)
async def create_job(
    file: UploadFile = File(...),
    show_video: bool = Form(False),
    save_interval_seconds: int = Form(5),
    save_interval_seconds_headless: int = Form(5),
    dead_overlay_opacity: float = Form(0.5),
    use_watermark_zone: bool = Form(False),
    watermark_x: int | None = Form(None),
    watermark_y: int | None = Form(None),
    watermark_width: int | None = Form(None),
    watermark_height: int | None = Form(None),
):
    job_id = str(uuid.uuid4())
    safe_name = _safe_filename(file.filename)
    upload_data = await _read_upload_bytes(file)
    save_upload_file(job_id, safe_name, upload_data)
    save_job_meta(job_id, safe_name)

    options = {
        "show_video": show_video,
        "save_interval_seconds": save_interval_seconds,
        "save_interval_seconds_headless": save_interval_seconds_headless,
        "dead_overlay_opacity": dead_overlay_opacity,
        "use_watermark_zone": use_watermark_zone,
        "watermark_x": watermark_x,
        "watermark_y": watermark_y,
        "watermark_width": watermark_width,
        "watermark_height": watermark_height,
    }
    queue = get_queue()
    queue.enqueue(
        process_video_job_task,
        job_id,
        options,
        job_id=job_id,
        result_ttl=7 * 24 * 3600,
        job_timeout=3600,
    )
    return CreateJobResponse(job_id=job_id, status="queued")


@app.get("/api/jobs", response_model=JobListResponse)
def list_jobs_endpoint(
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
):
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    items, total = list_jobs(limit=limit, offset=offset, search_q=q)
    return JobListResponse(jobs=[_list_item_to_schema(item) for item in items], total=total)


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=get_redis())
        return _job_response(job)
    except Exception:
        if not job_exists(job_id):
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from None
        return _db_job_response(job_id)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    redis_status = None
    try:
        job = Job.fetch(job_id, connection=get_redis())
        status = _rq_status_str(job).lower()
        redis_status = status
        if status in {"queued", "deferred", "scheduled"}:
            job.cancel()
            redis_status = "cancelled"
    except Exception:
        pass

    if not job_exists(job_id):
        if redis_status is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return {"job_id": job_id, "status": redis_status or "deleted"}

    delete_job_assets(job_id)
    return {"job_id": job_id, "status": redis_status or "deleted"}


@app.get("/api/jobs/{job_id}/artifacts/{name}")
def get_artifact(job_id: str, name: str):
    if name not in ARTIFACT_NAMES:
        raise HTTPException(status_code=404, detail="Unknown artifact")

    result = get_asset_by_api_name(job_id, name)
    if result is not None:
        data, content_type = result
        return Response(content=data, media_type=content_type)

    try:
        job = Job.fetch(job_id, connection=get_redis())
        status = _rq_status_str(job).lower()
        if status not in {"finished", "failed", "stopped"}:
            raise HTTPException(status_code=409, detail="Artifacts are not available yet")
        artifact_keys = _resolve_artifact_keys(job)
        if artifact_keys is not None and name not in artifact_keys:
            raise HTTPException(status_code=404, detail="Artifact not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}") from exc

    raise HTTPException(status_code=404, detail="Artifact file not found")
