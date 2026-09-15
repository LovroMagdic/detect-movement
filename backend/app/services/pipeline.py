import json
import os
import shutil
import sys
from dataclasses import dataclass


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import detect_movementv6_discovery as detect_movement  # noqa: E402


@dataclass
class PipelineOptions:
    show_video: bool = False
    save_interval_seconds: int = 5
    save_interval_seconds_headless: int = 5
    dead_overlay_opacity: float = 0.5
    dead_overlay_color_bgr: tuple[int, int, int] = (0, 0, 255)
    use_watermark_zone: bool = False
    watermark_x: int | None = None
    watermark_y: int | None = None
    watermark_width: int | None = None
    watermark_height: int | None = None


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
        elif event == "forest_overlay_start":
            mark("processing", 0.94, "Running land-cover segmentation on captured frames.", "forest_overlay")
        elif event == "forest_overlay_done":
            mark("processing", 0.97, "Land-cover segmentation overlay complete.", done_step="forest_overlay")

    result = detect_movement.run_pipeline(
        video_path=stable_video_path,
        output_dir=output_dir,
        show_video=options.show_video,
        save_interval_seconds=options.save_interval_seconds,
        save_interval_seconds_headless=options.save_interval_seconds_headless,
        dead_overlay_opacity=options.dead_overlay_opacity,
        dead_overlay_color_bgr=options.dead_overlay_color_bgr,
        use_watermark_zone=options.use_watermark_zone,
        watermark_x=options.watermark_x,
        watermark_y=options.watermark_y,
        watermark_width=options.watermark_width,
        watermark_height=options.watermark_height,
        stage_callback=on_pipeline_stage,
    )

    mark("finalizing", 0.95, "Writing metadata and finishing outputs.", "finalize_outputs")

    metadata = {
        "job_id": job_id,
        "has_video": bool(result.get("video_path")),
        "has_frames": bool(result.get("frames_dir")),
        "has_csv": bool(result.get("csv_path")),
        "has_map": bool(result.get("map_path")),
        "has_heatmap": bool(result.get("heatmap_path")),
        "has_overlay": bool(result.get("overlay_path")),
        "has_forest_overlay": bool(result.get("forest_overlay_path")),
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

    artifact_keys = list(required_files.keys())

    forest_path = result.get("forest_overlay_path", "")
    if forest_path and os.path.exists(forest_path):
        artifact_keys.append("forest_overlay")

    mark("done", 1.0, "Artifacts are ready for download.", done_step="finalize_outputs")

    return {"job_id": job_id, "artifacts": artifact_keys}
