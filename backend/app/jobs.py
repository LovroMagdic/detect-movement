import os
import tempfile

from rq import get_current_job

from app.services.pipeline import PipelineOptions, run_processing_job
from app.storage import delete_processing_assets, delete_upload_dir, ingest_directory, resolve_upload_video_path

STEP_LABELS = {
    "prepare_input": "Prepare input",
    "extract_and_detect": "Extract frames + detect motion",
    "stitch_map": "Stitch map",
    "generate_dead_mask": "Generate dead-tree mask heatmap",
    "overlay_render": "Render overlay",
    "forest_overlay": "Land-cover segmentation overlay",
    "finalize_outputs": "Finalize outputs",
}


def process_video_job(job_id: str, options: dict | None = None):
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
        from app.storage.service import ensure_storage_ready

        ensure_storage_ready()

        update(
            stage="queued",
            progress=0.0,
            detail="Waiting in queue for worker.",
            current_step=None,
            completed_steps=[],
        )
        upload_path = resolve_upload_video_path(job_id)
        with tempfile.TemporaryDirectory(prefix=f"job_{job_id}_") as tmp:
            output_dir = os.path.join(tmp, "output")
            os.makedirs(output_dir, exist_ok=True)

            pipeline_result = run_processing_job(
                job_id=job_id,
                input_video_path=upload_path,
                output_dir=output_dir,
                options=opts,
                stage_callback=update,
            )

            artifact_keys = ingest_directory(job_id, output_dir)
            for key in pipeline_result.get("artifacts", []):
                if key not in artifact_keys:
                    artifact_keys.append(key)
            artifact_keys = sorted(set(artifact_keys))

        update(
            stage="done",
            progress=1.0,
            detail="All artifacts are ready.",
            current_step=None,
            completed_steps=list(STEP_LABELS.keys()),
        )
        return {"job_id": job_id, "artifacts": artifact_keys}
    except Exception as exc:
        delete_processing_assets(job_id)
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
    finally:
        delete_upload_dir(job_id)
