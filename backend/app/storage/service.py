import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, cast, func, or_

from web_image import ensure_web_jpeg_bytes

from app.db.base import get_session, init_db
from app.db.models import JobAsset
from app.db.retry import retry_on_db_lock
from app.storage.uploads import UPLOAD_TEMP_ROOT, delete_upload_dir, get_upload_video_path

_WEB_IMAGE_API_NAMES = frozenset({"map", "heatmap", "overlay", "forest_overlay"})

API_ARTIFACT_TYPES = frozenset({"map", "heatmap", "overlay", "csv", "metadata", "forest_overlay"})

API_NAME_TO_ASSET: dict[str, tuple[str, str]] = {name: (name, "") for name in API_ARTIFACT_TYPES}

VIDEO_ASSET_TYPES = frozenset({"upload_video", "video"})


@contextmanager
def session_scope():
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def read_session_scope():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def _upsert_asset_row(
    session,
    job_id: str,
    asset_type: str,
    name: str,
    data: bytes,
    content_type: str,
) -> None:
    row = (
        session.query(JobAsset)
        .filter_by(job_id=job_id, asset_type=asset_type, name=name)
        .one_or_none()
    )
    if row is None:
        row = JobAsset(
            id=str(uuid.uuid4()),
            job_id=job_id,
            asset_type=asset_type,
            name=name,
            content_type=content_type,
            data=data,
            size_bytes=len(data),
        )
        session.add(row)
    else:
        row.content_type = content_type
        row.data = data
        row.size_bytes = len(data)


@retry_on_db_lock
def save_asset(
    job_id: str,
    asset_type: str,
    name: str,
    data: bytes,
    content_type: str,
) -> None:
    with session_scope() as session:
        _upsert_asset_row(session, job_id, asset_type, name, data, content_type)


@retry_on_db_lock
def save_assets_batch(
    job_id: str,
    assets: list[tuple[str, str, bytes, str]],
) -> None:
    if not assets:
        return
    with session_scope() as session:
        for asset_type, name, data, content_type in assets:
            _upsert_asset_row(session, job_id, asset_type, name, data, content_type)


def save_job_meta(job_id: str, filename: str) -> None:
    payload = json.dumps({"filename": filename}, indent=2).encode("utf-8")
    save_asset(job_id, "job_meta", "", payload, "application/json")


def get_job_filename(job_id: str) -> str | None:
    result = get_asset(job_id, "job_meta", "")
    if result is None:
        with read_session_scope() as session:
            legacy = (
                session.query(JobAsset)
                .filter_by(job_id=job_id, asset_type="upload_video")
                .one_or_none()
            )
            if legacy is not None:
                return legacy.name or "Unknown"
        return None
    data, _ = result
    try:
        meta = json.loads(data.decode("utf-8"))
        return meta.get("filename") or "Unknown"
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "Unknown"


def resolve_upload_video_path(job_id: str) -> str:
    filename = get_job_filename(job_id)
    if not filename:
        raise FileNotFoundError(f"No job metadata for job {job_id}")
    return get_upload_video_path(job_id, filename)


@retry_on_db_lock
def get_asset(job_id: str, asset_type: str, name: str = "") -> tuple[bytes, str] | None:
    with read_session_scope() as session:
        row = (
            session.query(JobAsset)
            .filter_by(job_id=job_id, asset_type=asset_type, name=name)
            .one_or_none()
        )
        if row is None:
            return None
        return row.data, row.content_type


def get_asset_by_api_name(job_id: str, api_name: str) -> tuple[bytes, str] | None:
    if api_name not in API_NAME_TO_ASSET:
        return None
    asset_type, name = API_NAME_TO_ASSET[api_name]
    result = get_asset(job_id, asset_type, name)
    if result is None or api_name not in _WEB_IMAGE_API_NAMES:
        return result
    data, content_type = result
    if not content_type.startswith("image/"):
        return result
    try:
        normalized = ensure_web_jpeg_bytes(data)
    except Exception:
        return result
    if normalized is None or normalized == data:
        return result
    save_asset(job_id, asset_type, name, normalized, "image/jpeg")
    return normalized, "image/jpeg"


@dataclass
class JobListItemData:
    job_id: str
    filename: str
    status: str
    updated_at: datetime


@dataclass
class JobSummaryData:
    job_id: str
    filename: str
    created_at: datetime
    updated_at: datetime
    artifacts: list[str]
    has_results: bool
    frame_count: int
    status: str


@retry_on_db_lock
def job_exists(job_id: str) -> bool:
    with read_session_scope() as session:
        return session.query(JobAsset.id).filter_by(job_id=job_id).first() is not None


def resolve_db_status(artifacts: list[str], has_results: bool, has_meta: bool) -> str:
    if has_results:
        return "finished"
    if has_meta:
        return "incomplete"
    return "unknown"


def _filename_from_meta_row(data: bytes | None, name: str) -> str | None:
    if data:
        try:
            meta = json.loads(data.decode("utf-8"))
            fn = meta.get("filename")
            if fn:
                return fn
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return name or None


def _list_items_for_job_ids(session, job_ids: list[str]) -> list[JobListItemData]:
    if not job_ids:
        return []

    agg_rows = (
        session.query(
            JobAsset.job_id,
            func.max(JobAsset.created_at).label("updated_at"),
        )
        .filter(JobAsset.job_id.in_(job_ids))
        .group_by(JobAsset.job_id)
        .all()
    )
    agg_by_id = {row.job_id: row for row in agg_rows}

    map_rows = (
        session.query(JobAsset.job_id)
        .filter(JobAsset.job_id.in_(job_ids), JobAsset.asset_type == "map")
        .distinct()
        .all()
    )
    jobs_with_map = {row[0] for row in map_rows}

    meta_rows = (
        session.query(JobAsset.job_id, JobAsset.asset_type, JobAsset.name, JobAsset.data)
        .filter(
            JobAsset.job_id.in_(job_ids),
            JobAsset.asset_type.in_(("job_meta", "upload_video")),
        )
        .all()
    )

    filenames: dict[str, str] = {}
    has_meta: dict[str, bool] = {jid: False for jid in job_ids}

    for row in meta_rows:
        if row.asset_type == "job_meta":
            has_meta[row.job_id] = True
            fn = _filename_from_meta_row(row.data, row.name)
            if fn:
                filenames[row.job_id] = fn
        elif row.asset_type == "upload_video":
            has_meta[row.job_id] = True
            filenames[row.job_id] = row.name or "Unknown"

    items: list[JobListItemData] = []
    for job_id in job_ids:
        agg = agg_by_id.get(job_id)
        if not agg:
            continue
        has_results = job_id in jobs_with_map
        status = resolve_db_status([], has_results, has_meta.get(job_id, False))
        items.append(
            JobListItemData(
                job_id=job_id,
                filename=filenames.get(job_id, "Unknown"),
                status=status,
                updated_at=agg.updated_at,
            )
        )
    return items


def _summaries_for_job_ids(session, job_ids: list[str]) -> list[JobSummaryData]:
    if not job_ids:
        return []

    agg_rows = (
        session.query(
            JobAsset.job_id,
            func.min(JobAsset.created_at).label("created_at"),
            func.max(JobAsset.created_at).label("updated_at"),
        )
        .filter(JobAsset.job_id.in_(job_ids))
        .group_by(JobAsset.job_id)
        .all()
    )
    agg_by_id = {row.job_id: row for row in agg_rows}

    meta_rows = (
        session.query(JobAsset.job_id, JobAsset.asset_type, JobAsset.name, JobAsset.data)
        .filter(
            JobAsset.job_id.in_(job_ids),
            JobAsset.asset_type.in_(("job_meta", "upload_video")),
        )
        .all()
    )

    artifact_rows = (
        session.query(JobAsset.job_id, JobAsset.asset_type)
        .filter(
            JobAsset.job_id.in_(job_ids),
            JobAsset.asset_type.in_(API_ARTIFACT_TYPES),
        )
        .distinct()
        .all()
    )

    frame_count_rows = (
        session.query(JobAsset.job_id, func.count(JobAsset.id))
        .filter(JobAsset.job_id.in_(job_ids), JobAsset.asset_type == "frame")
        .group_by(JobAsset.job_id)
        .all()
    )

    filenames: dict[str, str] = {}
    artifacts_by_job: dict[str, set[str]] = {jid: set() for jid in job_ids}
    frame_counts: dict[str, int] = {jid: 0 for jid in job_ids}
    has_meta: dict[str, bool] = {jid: False for jid in job_ids}

    for row in meta_rows:
        if row.asset_type == "job_meta":
            has_meta[row.job_id] = True
            fn = _filename_from_meta_row(row.data, row.name)
            if fn:
                filenames[row.job_id] = fn
        elif row.asset_type == "upload_video":
            has_meta[row.job_id] = True
            filenames[row.job_id] = row.name or "Unknown"

    for row in artifact_rows:
        artifacts_by_job[row.job_id].add(row.asset_type)

    for job_id, count in frame_count_rows:
        frame_counts[job_id] = count

    summaries: list[JobSummaryData] = []
    for job_id in job_ids:
        agg = agg_by_id.get(job_id)
        if not agg:
            continue
        artifact_list = sorted(artifacts_by_job.get(job_id, set()))
        has_results = "map" in artifact_list
        status = resolve_db_status(artifact_list, has_results, has_meta.get(job_id, False))
        summaries.append(
            JobSummaryData(
                job_id=job_id,
                filename=filenames.get(job_id, "Unknown"),
                created_at=agg.created_at,
                updated_at=agg.updated_at,
                artifacts=artifact_list,
                has_results=has_results,
                frame_count=frame_counts.get(job_id, 0),
                status=status,
            )
        )
    return summaries


@retry_on_db_lock
def list_jobs(
    limit: int = 50,
    offset: int = 0,
    search_q: str | None = None,
) -> tuple[list[JobListItemData], int]:
    with read_session_scope() as session:
        job_agg = session.query(
            JobAsset.job_id.label("job_id"),
            func.max(JobAsset.created_at).label("updated_at"),
        ).group_by(JobAsset.job_id)

        if search_q:
            q = f"%{search_q.strip()}%"
            matching_ids = (
                session.query(JobAsset.job_id)
                .filter(
                    or_(
                        (JobAsset.asset_type == "job_meta")
                        & (cast(JobAsset.data, String).ilike(q)),
                        (JobAsset.asset_type == "upload_video") & (JobAsset.name.ilike(q)),
                    )
                )
                .distinct()
            )
            job_agg = job_agg.filter(JobAsset.job_id.in_(matching_ids))

        agg = job_agg.subquery()
        query = session.query(agg.c.job_id).order_by(agg.c.updated_at.desc())

        total = query.count()
        job_id_rows = query.offset(offset).limit(limit).all()
        job_ids = [row[0] for row in job_id_rows]
        items = _list_items_for_job_ids(session, job_ids)
    return items, total


@retry_on_db_lock
def get_job_summary(job_id: str) -> JobSummaryData | None:
    with read_session_scope() as session:
        summaries = _summaries_for_job_ids(session, [job_id])
    return summaries[0] if summaries else None


@retry_on_db_lock
def list_api_artifacts(job_id: str) -> list[str]:
    with read_session_scope() as session:
        rows = (
            session.query(JobAsset.asset_type)
            .filter(JobAsset.job_id == job_id, JobAsset.asset_type.in_(API_ARTIFACT_TYPES))
            .distinct()
            .all()
        )
    return sorted({row[0] for row in rows})


PROCESSING_ASSET_TYPES = frozenset(
    {"frame", "map", "heatmap", "overlay", "forest_overlay", "csv", "metadata"}
)


@retry_on_db_lock
def delete_job_assets(job_id: str) -> None:
    with session_scope() as session:
        session.query(JobAsset).filter_by(job_id=job_id).delete()
    delete_upload_dir(job_id)


def delete_processing_assets(job_id: str) -> None:
    with session_scope() as session:
        session.query(JobAsset).filter(
            JobAsset.job_id == job_id,
            JobAsset.asset_type.in_(PROCESSING_ASSET_TYPES),
        ).delete(synchronize_session=False)


def clear_all_assets() -> int:
    with session_scope() as session:
        count = session.query(JobAsset).count()
        session.query(JobAsset).delete()
    return count


def purge_video_assets() -> int:
    with session_scope() as session:
        count = (
            session.query(JobAsset)
            .filter(JobAsset.asset_type.in_(VIDEO_ASSET_TYPES))
            .count()
        )
        session.query(JobAsset).filter(JobAsset.asset_type.in_(VIDEO_ASSET_TYPES)).delete(
            synchronize_session=False
        )
    return count


def ensure_storage_ready() -> None:
    init_db()
    os.makedirs(UPLOAD_TEMP_ROOT, exist_ok=True)
