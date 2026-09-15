import json
import os
import shutil

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UPLOAD_TEMP_ROOT = os.environ.get(
    "UPLOAD_TEMP_ROOT",
    os.path.join(APP_ROOT, "uploads-temp"),
)

os.makedirs(UPLOAD_TEMP_ROOT, exist_ok=True)


def upload_job_dir(job_id: str) -> str:
    path = os.path.join(UPLOAD_TEMP_ROOT, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_upload_file(job_id: str, filename: str, data: bytes) -> str:
    job_dir = upload_job_dir(job_id)
    target_path = os.path.join(job_dir, filename)
    with open(target_path, "wb") as f:
        f.write(data)
    return target_path


def get_upload_video_path(job_id: str, filename: str) -> str:
    path = os.path.join(UPLOAD_TEMP_ROOT, job_id, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Upload video not found for job {job_id}: {path}")
    return path


def delete_upload_dir(job_id: str) -> None:
    path = os.path.join(UPLOAD_TEMP_ROOT, job_id)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
