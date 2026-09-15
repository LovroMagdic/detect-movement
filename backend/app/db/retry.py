import time
from functools import wraps
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError

T = TypeVar("T")

_LOCK_ERRORS = ("database is locked", "database is busy")


def _is_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(token in msg for token in _LOCK_ERRORS)


def retry_on_db_lock(
    fn: Callable[..., T],
    *,
    max_attempts: int = 8,
    base_delay: float = 0.05,
) -> Callable[..., T]:
    @wraps(fn)
    def wrapper(*args, **kwargs) -> T:
        last_exc: OperationalError | None = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except OperationalError as exc:
                if not _is_lock_error(exc):
                    raise
                last_exc = exc
                if attempt < max_attempts - 1:
                    time.sleep(base_delay * (2**attempt))
        assert last_exc is not None
        raise last_exc

    return wrapper
