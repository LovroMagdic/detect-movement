import csv
import os
import time

import cv2
import numpy as np
import torch
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2

from web_image import prepare_web_jpeg_rgb

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_MODULE_DIR, "best_multiclass_model_v2_dice.pth")

INPUT_IMAGE_PATH = r"C:\Users\Lovro\Desktop\diplomski_rad\detect-movement\backend\data\jobs\37418f2c-121e-48fc-9122-ad37f7d28a94\captured_frames\389.jpg"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_HEIGHT, IMG_WIDTH = 512, 512
NUM_CLASSES = 4
OVERLAY_OPACITY = 0.4

CLASS_ROAD = 0
CLASS_GROUND = 1
CLASS_ROOF = 2
CLASS_TREE = 3

CLASS_OVERLAY_RGB: list[tuple[int, int, int] | None] = [
    None,
    (255, 0, 0),
    (0, 0, 255),
    (0, 255, 0),
]

CLASS_LABELS = {
    CLASS_ROAD: "road",
    CLASS_GROUND: "ground",
    CLASS_ROOF: "roof",
    CLASS_TREE: "tree",
}


def load_model(model_path, num_classes=NUM_CLASSES):
    model = smp.DeepLabV3Plus(
        encoder_name="resnet50",
        encoder_weights=None,
        in_channels=3,
        classes=num_classes,
        activation=None,
    ).to(DEVICE)
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    model.eval()
    return model


def _prepare_tensor(img_bgr):
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    transform = A.Compose([
        A.Resize(IMG_HEIGHT, IMG_WIDTH),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    tensor = transform(image=img_rgb)["image"].unsqueeze(0).to(DEVICE)
    return img_rgb, tensor


def get_class_map(model, img_bgr):
    h, w = img_bgr.shape[:2]
    _, tensor = _prepare_tensor(img_bgr)
    with torch.no_grad():
        logits = model(tensor)
    prediction = logits.argmax(dim=1).cpu().numpy().squeeze().astype(np.uint8)
    return cv2.resize(prediction, (w, h), interpolation=cv2.INTER_NEAREST)


def build_frame_overlay(img_bgr, class_map):
    base_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    has_overlay = np.zeros(class_map.shape, dtype=bool)

    for class_id, rgb in enumerate(CLASS_OVERLAY_RGB):
        if rgb is None:
            continue
        mask = class_map == class_id
        color = np.array(rgb, dtype=np.float32)
        base_rgb[mask] = OVERLAY_OPACITY * color + (1.0 - OVERLAY_OPACITY) * base_rgb[mask]
        has_overlay |= mask

    if not np.any(has_overlay):
        return img_bgr

    return cv2.cvtColor(base_rgb.astype(np.uint8), cv2.COLOR_RGB2BGR)


def stitch_forest_overlay(frames_dir, csv_path, output_dir, model_path=None):
    if model_path is None:
        model_path = MODEL_PATH

    if not os.path.exists(model_path):
        print(f"forest_overlay: model not found at {model_path}, skipping.")
        return None

    print(f"forest_overlay: loading model on {DEVICE} …")
    model = load_model(model_path)

    coords = []
    curr_x, curr_y = 0.0, 0.0
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            curr_x -= float(row["dx_total"])
            curr_y -= float(row["dy_total"])
            coords.append((curr_x, curr_y, row["frame_id"]))

    if not coords:
        return None

    first_img = cv2.imread(os.path.join(frames_dir, f"{coords[0][2]}.jpg"))
    if first_img is None:
        return None
    fh, fw = first_img.shape[:2]

    all_x = [c[0] for c in coords]
    all_y = [c[1] for c in coords]
    min_x, min_y = min(all_x), min(all_y)
    max_x, max_y = max(all_x), max(all_y)

    canvas_w = int(max_x - min_x) + fw
    canvas_h = int(max_y - min_y) + fh

    print(f"forest_overlay: creating canvas {canvas_w}x{canvas_h} for {len(coords)} frames …")
    forest_canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

    for x, y, fid in coords:
        img = cv2.imread(os.path.join(frames_dir, f"{fid}.jpg"))
        if img is None:
            continue

        class_map = get_class_map(model, img)
        frame_overlay = build_frame_overlay(img, class_map)

        sx, sy = int(x - min_x), int(y - min_y)
        f_roi = forest_canvas[sy:sy + fh, sx:sx + fw]
        is_empty = np.all(f_roi == 0, axis=-1)
        f_roi[is_empty] = frame_overlay[is_empty]

    gray_c = cv2.cvtColor(forest_canvas, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_c, 1, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        tx, ty, tw, th = cv2.boundingRect(np.vstack(cnts))
        forest_canvas = forest_canvas[ty:ty + th, tx:tx + tw]

    forest_rgb = cv2.cvtColor(forest_canvas, cv2.COLOR_BGR2RGB)
    output_path = os.path.join(output_dir, "forest_overlay_map.jpg")
    with open(output_path, "wb") as f:
        f.write(prepare_web_jpeg_rgb(forest_rgb))
    print(f"forest_overlay: saved → {output_path}")
    return output_path


def process_image(image_path):
    original_img = cv2.imread(image_path)
    if original_img is None:
        raise FileNotFoundError(f"Could not read image at {image_path}")
    img_rgb, tensor = _prepare_tensor(original_img)
    return original_img, img_rgb, tensor


def run_inference(model, image_path):
    import matplotlib.pyplot as plt

    orig_bgr, orig_rgb, input_tensor = process_image(image_path)

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()
    start_time = time.perf_counter()

    with torch.no_grad():
        logits = model(input_tensor)
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()

    inference_ms = (time.perf_counter() - start_time) * 1000
    print(f"Inference Time: {inference_ms:.2f} ms")

    class_map = logits.argmax(dim=1).cpu().numpy().squeeze().astype(np.uint8)
    h, w = orig_bgr.shape[:2]
    class_map = cv2.resize(class_map, (w, h), interpolation=cv2.INTER_NEAREST)

    combined_bgr = build_frame_overlay(orig_bgr, class_map)
    combined_rgb = cv2.cvtColor(combined_bgr, cv2.COLOR_BGR2RGB)

    plt.figure(figsize=(14, 6))
    plt.subplot(1, 3, 1)
    plt.imshow(orig_rgb)
    plt.title("Original")
    plt.axis("off")
    plt.subplot(1, 3, 2)
    plt.imshow(class_map, cmap="tab10", vmin=0, vmax=NUM_CLASSES - 1)
    plt.title(f"Classes ({inference_ms:.1f} ms)")
    plt.axis("off")
    plt.subplot(1, 3, 3)
    plt.imshow(combined_rgb)
    plt.title("Overlay (tree / road / roof)")
    plt.axis("off")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    if not os.path.exists(MODEL_PATH):
        print(f"Error: Could not find {MODEL_PATH}.")
    else:
        print(f"Running inference on {DEVICE} …")
        forest_model = load_model(MODEL_PATH)
        run_inference(forest_model, INPUT_IMAGE_PATH)
