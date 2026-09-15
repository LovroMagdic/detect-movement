import json
import mimetypes
import os

from web_image import ensure_web_jpeg_bytes

from app.storage.service import API_ARTIFACT_TYPES, save_assets_batch

OUTPUT_FILE_MAP: dict[str, str] = {
    "final_stitched_map.jpg": "map",
    "dead_tree_heatmap.jpg": "heatmap",
    "final_overlay_result.jpg": "overlay",
    "forest_overlay_map.jpg": "forest_overlay",
    "movement_data.csv": "csv",
    "metadata.json": "metadata",
}


def _guess_content_type(filename: str, asset_type: str) -> str:
    if asset_type == "csv":
        return "text/csv"
    if asset_type == "metadata":
        return "application/json"
    if asset_type in {"map", "heatmap", "overlay", "forest_overlay", "frame"}:
        return "image/jpeg"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def ingest_directory(job_id: str, dir_path: str) -> list[str]:
    artifact_keys: list[str] = []
    batch: list[tuple[str, str, bytes, str]] = []

    for filename, asset_type in OUTPUT_FILE_MAP.items():
        path = os.path.join(dir_path, filename)
        if not os.path.isfile(path):
            continue
        data = _read_file(path)
        if asset_type in {"map", "heatmap", "overlay", "forest_overlay"}:
            normalized = ensure_web_jpeg_bytes(data)
            if normalized is not None:
                data = normalized
        if asset_type == "metadata":
            try:
                meta = json.loads(data.decode("utf-8"))
                meta.pop("video_path", None)
                meta.pop("frames_dir", None)
                meta.pop("csv_path", None)
                meta.pop("map_path", None)
                meta.pop("heatmap_path", None)
                meta.pop("overlay_path", None)
                meta.pop("forest_overlay_path", None)
                data = json.dumps(meta, indent=2).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        batch.append((asset_type, "", data, _guess_content_type(filename, asset_type)))
        if asset_type in API_ARTIFACT_TYPES:
            artifact_keys.append(asset_type)

    frames_dir = os.path.join(dir_path, "captured_frames")
    if os.path.isdir(frames_dir):
        for frame_name in sorted(os.listdir(frames_dir)):
            if not frame_name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            frame_path = os.path.join(frames_dir, frame_name)
            if not os.path.isfile(frame_path):
                continue
            batch.append(
                (
                    "frame",
                    frame_name,
                    _read_file(frame_path),
                    _guess_content_type(frame_name, "frame"),
                )
            )

    save_assets_batch(job_id, batch)
    return sorted(set(artifact_keys))
