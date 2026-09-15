#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.base import DB_PATH, engine  # noqa: E402
from app.db.models import JobAsset  # noqa: E402
from app.storage.service import UPLOAD_TEMP_ROOT, clear_all_assets, purge_video_assets  # noqa: E402


def _clear_upload_temp() -> int:
    if not os.path.isdir(UPLOAD_TEMP_ROOT):
        return 0
    removed = 0
    for entry in os.listdir(UPLOAD_TEMP_ROOT):
        path = os.path.join(UPLOAD_TEMP_ROOT, entry)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
        elif os.path.isfile(path):
            os.remove(path)
            removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear all job data from the database.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required flag to actually delete data.",
    )
    parser.add_argument(
        "--purge-videos-only",
        action="store_true",
        help="Delete only legacy upload_video and video blobs (keep frames and results).",
    )
    args = parser.parse_args()

    if not args.confirm:
        print("Refusing to run without --confirm")
        sys.exit(1)

    if args.purge_videos_only:
        count = purge_video_assets()
        print(f"Deleted {count} video blob row(s).")
    else:
        count = clear_all_assets()
        print(f"Deleted {count} job_assets row(s).")
        temp_dirs = _clear_upload_temp()
        print(f"Cleared {temp_dirs} entr(ies) under {UPLOAD_TEMP_ROOT}")

        with engine.connect() as conn:
            conn.exec_driver_sql("VACUUM")
            conn.commit()
        print(f"VACUUM completed on {DB_PATH}")


if __name__ == "__main__":
    main()
