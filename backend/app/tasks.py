"""Lightweight RQ task entrypoints.

Keep this module free of heavy processing imports so API startup does not require
all worker/runtime dependencies.
"""


def process_video_job_task(job_id: str, input_video_path: str, output_dir: str, options: dict | None = None):
    # Import lazily so worker-only dependencies are loaded only when task runs.
    from app.jobs import process_video_job

    return process_video_job(job_id, input_video_path, output_dir, options)
