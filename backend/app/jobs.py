from rq import get_current_job

from app.services.pipeline import PipelineOptions, run_processing_job

STEP_LABELS = {
    "prepare_input": "Prepare input",
    "extract_and_detect": "Extract frames + detect motion",
    "stitch_map": "Stitch map",
    "generate_dead_mask": "Generate dead-tree mask heatmap",
    "overlay_render": "Render overlay",
    "finalize_outputs": "Finalize outputs",
}


def process_video_job(job_id: str, input_video_path: str, output_dir: str, options: dict | None = None):
    job = get_current_job()
    opts = PipelineOptions(**(options or {}))

    def _set_step_states(current_step: str | None, completed_steps: list[str] | None, failed: bool = False):
        completed = set(completed_steps or [])
        step_states = []
        for key, label in STEP_LABELS.items():
            state = "pending"
            if key in completed:
                state = "done"
            if key == current_step:
                state = "failed" if failed else "running"
            step_states.append({"key": key, "label": label, "state": state})
        return step_states

    def update(
        stage: str,
        progress: float,
        detail: str | None = None,
        current_step: str | None = None,
        completed_steps: list[str] | None = None,
    ):
        if job is None:
            return
        job.meta["stage"] = stage
        job.meta["progress"] = progress
        if detail:
            job.meta["stage_detail"] = detail
        if current_step is not None:
            job.meta["current_step"] = current_step
        if completed_steps is not None:
            job.meta["completed_steps"] = completed_steps
        job.meta["steps"] = _set_step_states(job.meta.get("current_step"), job.meta.get("completed_steps"))
        job.save_meta()

    try:
        update(
            stage="queued",
            progress=0.0,
            detail="Waiting in queue for worker.",
            current_step=None,
            completed_steps=[],
        )
        result = run_processing_job(
            job_id=job_id,
            input_video_path=input_video_path,
            output_dir=output_dir,
            options=opts,
            stage_callback=update,
        )
        update(
            stage="done",
            progress=1.0,
            detail="All artifacts are ready.",
            current_step=None,
            completed_steps=list(STEP_LABELS.keys()),
        )
        return result
    except Exception as exc:
        if job is not None:
            job.meta["stage"] = "failed"
            job.meta["progress"] = 1.0
            job.meta["stage_detail"] = "Processing failed."
            job.meta["error"] = str(exc)
            job.meta["steps"] = _set_step_states(
                job.meta.get("current_step"),
                job.meta.get("completed_steps"),
                failed=True,
            )
            job.save_meta()
        raise

