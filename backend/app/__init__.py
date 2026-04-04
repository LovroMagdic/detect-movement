"""Backend application package."""

# RQ resolves task callables via dotted paths (e.g. `app.tasks.process_video_job_task`).
# Expose `tasks` for stable attribute resolution without importing heavy worker modules.
from . import tasks  # noqa: F401

