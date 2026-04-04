import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import detect_movementv3  # noqa: E402


def build_dead_map(crop_bounds):
    return detect_movementv3.build_dead_weight_map(crop_bounds)

