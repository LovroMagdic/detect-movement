import os
import re
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from rq.job import Job

from app.queue import get_queue, get_redis
from app.schemas import CreateJobResponse, JobStatusResponse
from app.tasks import process_video_job_task


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_ROOT = os.path.join(APP_ROOT, "data")
UPLOAD_ROOT = os.path.join(DATA_ROOT, "uploads")
JOBS_ROOT = os.path.join(DATA_ROOT, "jobs")
os.makedirs(UPLOAD_ROOT, exist_ok=True)
os.makedirs(JOBS_ROOT, exist_ok=True)

ARTIFACT_NAMES = {"map", "heatmap", "overlay", "csv", "metadata"}
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks

app = FastAPI(title="Detect Motion API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _rq_status_str(job: Job) -> str:
    st = job.get_status(refresh=True)
    if hasattr(st, "value"):
        return str(st.value)
    return str(st)


def _job_response(job: Job) -> JobStatusResponse:
    status = _rq_status_str(job)
    result = job.result if isinstance(job.result, dict) else None
    artifacts = None
    if result and isinstance(result.get("artifacts"), dict):
        artifacts = {k: f"/api/jobs/{job.id}/artifacts/{k}" for k in result["artifacts"].keys()}
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


def _safe_filename(name: str | None) -> str:
    if not name:
        return "upload.bin"
    base = os.path.basename(name)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    return safe or "upload.bin"


async def _write_upload_file(file: UploadFile, target_path: str) -> None:
    with open(target_path, "wb") as out:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            out.write(chunk)
    await file.close()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/jobs", response_model=CreateJobResponse)
async def create_job(
    file: UploadFile = File(...),
    show_video: bool = Form(False),
    save_interval_seconds: int = Form(5),
    save_interval_seconds_headless: int = Form(5),
    dead_overlay_opacity: float = Form(0.45),
):
    job_id = str(uuid.uuid4())
    safe_name = _safe_filename(file.filename)
    upload_path = os.path.join(UPLOAD_ROOT, f"{job_id}_{safe_name}")
    job_output_dir = os.path.join(JOBS_ROOT, job_id)
    os.makedirs(job_output_dir, exist_ok=True)
    await _write_upload_file(file, upload_path)

    options = {
        "show_video": show_video,
        "save_interval_seconds": save_interval_seconds,
        "save_interval_seconds_headless": save_interval_seconds_headless,
        "dead_overlay_opacity": dead_overlay_opacity,
    }
    queue = get_queue()
    queue.enqueue(
        process_video_job_task,
        job_id,
        upload_path,
        job_output_dir,
        options,
        job_id=job_id,
        result_ttl=7 * 24 * 3600,
    )
    return CreateJobResponse(job_id=job_id, status="queued")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=get_redis())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}") from exc
    return _job_response(job)


@app.get("/api/jobs/{job_id}/artifacts/{name}")
def get_artifact(job_id: str, name: str):
    if name not in ARTIFACT_NAMES:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    try:
        job = Job.fetch(job_id, connection=get_redis())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}") from exc
    result = job.result if isinstance(job.result, dict) else None
    if not result or "artifacts" not in result:
        raise HTTPException(status_code=409, detail="Artifacts are not available yet")
    artifact_path = result["artifacts"].get(name)
    if not artifact_path or not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(artifact_path)

