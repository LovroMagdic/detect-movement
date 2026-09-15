def process_video_job_task(job_id: str, options: dict | None = None):
    from app.jobs import process_video_job

    return process_video_job(job_id, options)
