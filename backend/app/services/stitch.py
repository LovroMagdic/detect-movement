import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import detect_movementv3  # noqa: E402


def stitch_from_csv() -> tuple[int, int, int, int] | None:
    return detect_movementv3.stitch_map_from_csv()

