import json
import os
import shutil
import sys
from dataclasses import dataclass


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import detect_movementv3  # noqa: E402


@dataclass
class PipelineOptions:
    show_video: bool = False
    save_interval_seconds: int = 5
    save_interval_seconds_headless: int = 5
    dead_overlay_opacity: float = 0.45
    dead_overlay_color_bgr: tuple[int, int, int] = (0, 0, 255)


def run_processing_job(
    job_id: str,
    input_video_path: str,
    output_dir: str,
    options: PipelineOptions,
    stage_callback=None,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    completed_steps: list[str] = []

    def mark(
        stage: str,
        progress: float,
        detail: str,
        current_step: str | None = None,
        done_step: str | None = None,
    ):
        if done_step and done_step not in completed_steps:
            completed_steps.append(done_step)
        if stage_callback:
            stage_callback(stage, progress, detail, current_step, completed_steps.copy())

    mark("preparing", 0.05, "Preparing paths and copying input video.", "prepare_input")

    video_name = os.path.basename(input_video_path)
    stable_video_path = os.path.join(output_dir, video_name)
    if os.path.abspath(input_video_path) != os.path.abspath(stable_video_path):
        shutil.copy2(input_video_path, stable_video_path)
    mark("preparing", 0.1, "Input prepared.", done_step="prepare_input")

    mark("processing", 0.2, "Extracting frames and detecting motion.", "extract_and_detect")

    def on_pipeline_stage(event: str):
        if event == "extract_and_detect_start":
            mark("processing", 0.2, "Extracting frames and detecting motion.", "extract_and_detect")
        elif event == "extract_and_detect_done":
            mark("processing", 0.55, "Frame extraction and motion detection complete.", done_step="extract_and_detect")
        elif event == "stitch_map_start":
            mark("processing", 0.6, "Stitching map from motion CSV.", "stitch_map")
        elif event == "stitch_map_done":
            mark("processing", 0.72, "Stitched map generated.", done_step="stitch_map")
        elif event == "generate_dead_mask_start":
            mark("processing", 0.75, "Generating dead-tree mask heatmap.", "generate_dead_mask")
        elif event == "generate_dead_mask_done":
            mark("processing", 0.86, "Dead-tree mask heatmap generated.", done_step="generate_dead_mask")
        elif event == "overlay_render_start":
            mark("processing", 0.9, "Rendering dead-tree overlay.", "overlay_render")
        elif event == "overlay_render_done":
            mark("processing", 0.93, "Overlay rendered.", done_step="overlay_render")

    result = detect_movementv3.run_pipeline(
        video_path=stable_video_path,
        output_dir=output_dir,
        show_video=options.show_video,
        save_interval_seconds=options.save_interval_seconds,
        save_interval_seconds_headless=options.save_interval_seconds_headless,
        dead_overlay_opacity=options.dead_overlay_opacity,
        dead_overlay_color_bgr=options.dead_overlay_color_bgr,
        stage_callback=on_pipeline_stage,
    )

    mark("finalizing", 0.95, "Writing metadata and finishing outputs.", "finalize_outputs")

    metadata = {
        "job_id": job_id,
        "video_path": result["video_path"],
        "frames_dir": result["frames_dir"],
        "csv_path": result["csv_path"],
        "map_path": result["map_path"],
        "heatmap_path": result["heatmap_path"],
        "overlay_path": result["overlay_path"],
    }
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    required_files = {
        "map": result["map_path"],
        "heatmap": result["heatmap_path"],
        "overlay": result["overlay_path"],
        "csv": result["csv_path"],
        "metadata": metadata_path,
    }
    missing = [f"{name}={path}" for name, path in required_files.items() if not os.path.exists(path)]
    if missing:
        raise FileNotFoundError("Missing expected output artifacts: " + ", ".join(missing))

    artifacts = {
        **required_files,
    }

    mark("done", 1.0, "Artifacts are ready for download.", done_step="finalize_outputs")

    return {"job_id": job_id, "artifacts": artifacts}

