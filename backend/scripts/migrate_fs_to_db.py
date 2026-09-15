#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.storage.ingest import OUTPUT_FILE_MAP, _guess_content_type  # noqa: E402
from app.storage.service import ensure_storage_ready, save_asset, save_job_meta  # noqa: E402

DATA_ROOT = os.path.join(BACKEND_ROOT, "data")
UPLOAD_ROOT = os.path.join(DATA_ROOT, "uploads")
JOBS_ROOT = os.path.join(DATA_ROOT, "jobs")


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _job_id_from_upload(filename: str) -> tuple[str, str] | None:
    match = re.match(
        r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_(.+)$",
        filename,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def migrate_upload_meta() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not os.path.isdir(UPLOAD_ROOT):
        return counts

    for entry in os.listdir(UPLOAD_ROOT):
        path = os.path.join(UPLOAD_ROOT, entry)
        if not os.path.isfile(path):
            continue
        parsed = _job_id_from_upload(entry)
        if not parsed:
            print(f"skip upload (unrecognized name): {entry}")
            continue
        job_id, original_name = parsed
        save_job_meta(job_id, original_name)
        counts[job_id] = counts.get(job_id, 0) + 1
        print(f"job_meta: {job_id} <- {original_name}")
    return counts


def migrate_job_dir(job_id: str, job_dir: str) -> int:
    imported = 0

    for filename, asset_type in OUTPUT_FILE_MAP.items():
        path = os.path.join(job_dir, filename)
        if not os.path.isfile(path):
            continue
        data = _read_file(path)
        if asset_type == "metadata":
            try:
                meta = json.loads(data.decode("utf-8"))
                for key in (
                    "video_path",
                    "frames_dir",
                    "csv_path",
                    "map_path",
                    "heatmap_path",
                    "overlay_path",
                    "forest_overlay_path",
                ):
                    meta.pop(key, None)
                data = json.dumps(meta, indent=2).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        save_asset(
            job_id,
            asset_type,
            "",
            data,
            _guess_content_type(filename, asset_type),
        )
        imported += 1
        print(f"  {asset_type}: {filename}")

    frames_dir = os.path.join(job_dir, "captured_frames")
    if os.path.isdir(frames_dir):
        frame_count = 0
        for frame_name in sorted(os.listdir(frames_dir)):
            frame_path = os.path.join(frames_dir, frame_name)
            if not os.path.isfile(frame_path):
                continue
            save_asset(
                job_id,
                "frame",
                frame_name,
                _read_file(frame_path),
                _guess_content_type(frame_name, "frame"),
            )
            imported += 1
            frame_count += 1
        print(f"  frames: {frame_count} files")

    return imported


def migrate_jobs() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not os.path.isdir(JOBS_ROOT):
        return counts

    for job_id in sorted(os.listdir(JOBS_ROOT)):
        job_dir = os.path.join(JOBS_ROOT, job_id)
        if not os.path.isdir(job_dir):
            continue
        print(f"job: {job_id}")
        counts[job_id] = migrate_job_dir(job_id, job_dir)
    return counts


def main() -> None:
    ensure_storage_ready()
    print(f"Data root: {DATA_ROOT}")
    print("Note: videos are not imported (frames and pipeline outputs only).")
    meta_counts = migrate_upload_meta()
    job_counts = migrate_jobs()
    print("\nSummary")
    print(f"  job_meta rows: {sum(meta_counts.values())}")
    print(f"  jobs processed: {len(job_counts)}")
    print(f"  files imported: {sum(job_counts.values())}")


if __name__ == "__main__":
    main()
