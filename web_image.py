from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

MAX_WEB_IMAGE_DIMENSION = 16384
MAX_WEB_IMAGE_PIXELS = 268_435_456


def cap_image_for_web(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    scale = 1.0
    if max(h, w) > MAX_WEB_IMAGE_DIMENSION:
        scale = min(scale, MAX_WEB_IMAGE_DIMENSION / max(h, w))
    if w * h > MAX_WEB_IMAGE_PIXELS:
        scale = min(scale, (MAX_WEB_IMAGE_PIXELS / (w * h)) ** 0.5)
    if scale >= 1.0:
        return img
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def heatmap_to_web_bgr(heatmap: np.ndarray) -> np.ndarray:
    if heatmap.ndim == 3:
        return heatmap
    red = np.zeros((heatmap.shape[0], heatmap.shape[1], 3), dtype=np.uint8)
    red[:, :] = (0, 0, 255)
    return cv2.bitwise_and(red, red, mask=heatmap)


def prepare_web_jpeg(img: np.ndarray, quality: int = 90) -> bytes:
    if img.ndim == 2:
        img = heatmap_to_web_bgr(img)
    elif img.shape[2] == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = cap_image_for_web(img)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("Failed to encode JPEG for web delivery")
    return buf.tobytes()


def prepare_web_jpeg_rgb(img_rgb: np.ndarray, quality: int = 90) -> bytes:
    if img_rgb.ndim == 2:
        img_rgb = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2RGB)
    elif img_rgb.shape[2] == 1:
        img_rgb = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2RGB)
    img_rgb = cap_image_for_web(img_rgb)
    buf = io.BytesIO()
    Image.fromarray(img_rgb.astype(np.uint8)).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def ensure_web_jpeg_bytes(data: bytes) -> bytes | None:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        return prepare_web_jpeg(img)
    if img.shape[2] == 3:
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return prepare_web_jpeg_rgb(img_rgb)
    return prepare_web_jpeg(img)
