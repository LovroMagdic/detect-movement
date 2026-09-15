from __future__ import annotations

import argparse
import os
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(BACKEND_ROOT, ".."))
sys.path[:0] = [REPO_ROOT, BACKEND_ROOT]

from web_image import ensure_web_jpeg_bytes  # noqa: E402

from app.db.base import init_db  # noqa: E402
from app.storage.service import (  # noqa: E402
    get_asset,
    list_api_artifacts,
    save_asset,
    session_scope,
)
from app.db.models import JobAsset  # noqa: E402

IMAGE_TYPES = ("map", "heatmap", "overlay", "forest_overlay")


def normalize_job(job_id: str, dry_run: bool = False) -> int:
    updated = 0
    for asset_type in IMAGE_TYPES:
        result = get_asset(job_id, asset_type, "")
        if result is None:
            continue
        data, _ = result
        fixed = ensure_web_jpeg_bytes(data)
        if fixed is None or fixed == data:
            continue
        updated += 1
        if not dry_run:
            save_asset(job_id, asset_type, "", fixed, "image/jpeg")
            print(f"  {asset_type}: {len(data)} -> {len(fixed)} bytes")
        else:
            print(f"  would update {asset_type}: {len(data)} -> {len(fixed)} bytes")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", help="Only normalize this job")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()

    if args.job_id:
        job_ids = [args.job_id]
    else:
        with session_scope() as session:
            rows = session.query(JobAsset.job_id).filter(
                JobAsset.asset_type.in_(IMAGE_TYPES)
            ).distinct().all()
        job_ids = sorted({row[0] for row in rows})

    total = 0
    for job_id in job_ids:
        count = normalize_job(job_id, dry_run=args.dry_run)
        if count:
            print(f"{job_id}: {count} asset(s)")
            total += count
    print(f"Done. Updated {total} asset(s) across {len(job_ids)} job(s).")


if __name__ == "__main__":
    main()
