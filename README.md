# Detect Motion Web Pipeline

Local web app for video processing:
- upload a video in the browser
- backend runs motion + stitching + dead-tree heatmap + overlay
- frontend displays map/heatmap layers with zoom + pan

## Architecture

- Frontend: React + TypeScript (`frontend/`)
- API: FastAPI (`backend/app/main.py`)
- Queue: Redis + RQ worker (`backend/app/jobs.py`)
- Processing core: `detect_movementv3.py` and `image_preprocessing.py`

## Prerequisites

- Python 3.10+
- Redis running locally on `redis://localhost:6379/0`
- Node.js + npm (for frontend)
- Docker Desktop (optional, recommended for one-command setup)

## Docker (all services in containers)

From project root:

```bash
docker compose up --build
```

This starts:
- `redis` on `localhost:6379`
- `api` on `localhost:8000`
- `worker` (RQ queue consumer)
- `frontend` on `localhost:5173`

Open:
- Frontend: `http://localhost:5173`
- API health: `http://localhost:8000/api/health`

Stop containers:

```bash
docker compose down
```

Rebuild after dependency/code changes:

```bash
docker compose up --build
```

## 1) Start Redis

Use your local Redis service or run Docker:

```bash
docker run --name detect-motion-redis -p 6379:6379 redis:7
```

## 2) Start backend API

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 3) Start RQ worker

In a second terminal:

```bash
cd backend
rq worker detect-motion
```

If needed, set Redis URL:

```bash
set REDIS_URL=redis://localhost:6379/0
```

## 4) Start frontend

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## API endpoints

- `POST /api/jobs` (multipart upload: `file`)
- `GET /api/jobs/{job_id}` (status/progress)
- `GET /api/jobs/{job_id}/artifacts/{name}` where `name` is one of:
  - `map`
  - `heatmap`
  - `overlay`
  - `csv`
  - `metadata`

## Notes

- Processing artifacts are written under `backend/data/jobs/{job_id}/`.
- Existing script mode still works:

```bash
python detect_movementv3.py
```

