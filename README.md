# Detect Motion Web Pipeline

Upload a video in the browser; the backend runs motion detection, stitching, dead-tree heatmap and overlay, and the frontend shows the resulting map layers.

- Frontend: React + TypeScript (`frontend/`)
- API: FastAPI (`backend/app/main.py`)
- Queue: Redis + RQ worker (`backend/app/jobs.py`)
- Storage: SQLite (`backend/database/app.db`)
- Processing: `detect_movementv6_discovery.py`, `forest_overlay.py`, `dead_tree_model.py`

**Required:** the model files `best_multiclass_model_v2_dice.pth` and `best_dead_trees_combined.pth` must be in the project root.

## Run with Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:5173 (API health check: http://localhost:8000/api/health).

Stop with `docker compose down`.

## Run locally (without Docker)

Requires Python 3.10+, Node.js, and Redis. RQ workers don't run natively on Windows, so on Windows use Docker or WSL for the worker.

Use a separate terminal for each step, starting in the project root:

```bash
# 1. Redis
docker run --name detect-motion-redis -p 6379:6379 redis:7

# 2. API
cd backend
pip install torch torchvision
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Worker
cd backend
rq worker detect-motion

# 4. Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. To use a different Redis, set `REDIS_URL` (default `redis://localhost:6379/0`).

## Run the script only

Set `VIDEO_PATH` at the top of `detect_movementv6_discovery.py`, then run:

```bash
python detect_movementv6_discovery.py
```

Output is written to `final_output/`.

## API endpoints

- `GET /api/jobs`: list jobs (`limit`, `offset`, `q`)
- `POST /api/jobs`: upload a video (multipart field `file`)
- `GET /api/jobs/{job_id}`: job status and progress
- `DELETE /api/jobs/{job_id}`: cancel the job and delete its data
- `GET /api/jobs/{job_id}/artifacts/{name}`: `name` is `map`, `heatmap`, `overlay`, `csv` or `metadata`

## Maintenance

```bash
cd backend
python scripts/clear_database.py --confirm                       # delete all data
python scripts/clear_database.py --confirm --purge-videos-only   # delete old video blobs only
python scripts/migrate_fs_to_db.py                               # import legacy backend/data/ outputs
```
