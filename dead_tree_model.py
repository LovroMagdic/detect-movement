import os

import cv2
import numpy as np
import torch

from forest_overlay import load_model, _prepare_tensor

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_MODULE_DIR, "best_dead_trees_combined.pth")

NUM_CLASSES = 2
CLASS_DEAD_TREE = 1

_model = None


def get_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Dead-tree model not found at {MODEL_PATH}")
        _model = load_model(MODEL_PATH, num_classes=NUM_CLASSES)
    return _model


def compute_dead_mask(img_bgr):
    """Return a uint8 mask (255 = dead tree, 0 = other) at the frame's resolution."""
    if img_bgr is None:
        return None
    h, w = img_bgr.shape[:2]
    _, tensor = _prepare_tensor(img_bgr)
    with torch.no_grad():
        logits = get_model()(tensor)
    prediction = logits.argmax(dim=1).cpu().numpy().squeeze().astype(np.uint8)
    mask = np.where(prediction == CLASS_DEAD_TREE, 255, 0).astype(np.uint8)
    return cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
