import cv2
import numpy as np
import os
import csv

import image_preprocessing

VIDEO_PATH = 'video5.mp4'
FRAMES_DIR = f'frames_{VIDEO_PATH}'
CSV_PATH = f'movement_data_{VIDEO_PATH}.csv'
MAP_OUTPUT_PATH = f'stitched_map_{VIDEO_PATH}.jpg'
DEAD_HEATMAP_PATH = f'dead_heatmap_{VIDEO_PATH}.png'
MAP_DEAD_OVERLAY_PATH = f'stitched_map_dead_overlay_{VIDEO_PATH}.jpg'
DEAD_OVERLAY_OPACITY = 0.45
DEAD_OVERLAY_COLOR_BGR = (0, 0, 255)

SAVE_INTERVAL_SECONDS = 5
SHOW_VIDEO = False
# Use a larger value in headless mode to reduce disk I/O.
SAVE_INTERVAL_SECONDS_HEADLESS = SAVE_INTERVAL_SECONDS

WATERMARK_HEIGHT_PCT = 0.25
WATERMARK_WIDTH_PCT = 0.15

feature_params = dict(maxCorners=100, qualityLevel=0.5, minDistance=20, blockSize=7)
lk_params = dict(winSize=(21, 21), maxLevel=3, 
                 criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))


def configure_pipeline_paths(video_path, output_dir):
    """Configure global output locations for a specific video/job."""
    global VIDEO_PATH, FRAMES_DIR, CSV_PATH, MAP_OUTPUT_PATH, DEAD_HEATMAP_PATH, MAP_DEAD_OVERLAY_PATH
    os.makedirs(output_dir, exist_ok=True)
    video_name = os.path.basename(video_path)
    VIDEO_PATH = video_path
    FRAMES_DIR = os.path.join(output_dir, f"frames_{video_name}")
    CSV_PATH = os.path.join(output_dir, f"movement_data_{video_name}.csv")
    MAP_OUTPUT_PATH = os.path.join(output_dir, f"stitched_map_{video_name}.jpg")
    DEAD_HEATMAP_PATH = os.path.join(output_dir, f"dead_heatmap_{video_name}.png")
    MAP_DEAD_OVERLAY_PATH = os.path.join(output_dir, f"stitched_map_dead_overlay_{video_name}.jpg")


def run_pipeline(
    video_path,
    output_dir,
    show_video=False,
    save_interval_seconds=5,
    save_interval_seconds_headless=None,
    dead_overlay_opacity=0.45,
    dead_overlay_color_bgr=(0, 0, 255),
    stage_callback=None,
):
    """Run full processing pipeline and return generated artifact paths."""
    global SHOW_VIDEO, SAVE_INTERVAL_SECONDS, SAVE_INTERVAL_SECONDS_HEADLESS, DEAD_OVERLAY_OPACITY, DEAD_OVERLAY_COLOR_BGR

    configure_pipeline_paths(video_path, output_dir)
    SHOW_VIDEO = bool(show_video)
    SAVE_INTERVAL_SECONDS = int(save_interval_seconds)
    if save_interval_seconds_headless is None:
        save_interval_seconds_headless = SAVE_INTERVAL_SECONDS
    SAVE_INTERVAL_SECONDS_HEADLESS = int(save_interval_seconds_headless)
    DEAD_OVERLAY_OPACITY = float(dead_overlay_opacity)
    DEAD_OVERLAY_COLOR_BGR = tuple(dead_overlay_color_bgr)

    if stage_callback:
        stage_callback("extract_and_detect_start")
    record_video_data()
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Motion CSV was not generated: {CSV_PATH}")
    if stage_callback:
        stage_callback("extract_and_detect_done")

    if stage_callback:
        stage_callback("stitch_map_start")
    stitch_bounds = stitch_map_from_csv()
    if stitch_bounds is None or not os.path.exists(MAP_OUTPUT_PATH):
        raise FileNotFoundError(f"Stitched map was not generated: {MAP_OUTPUT_PATH}")
    if stage_callback:
        stage_callback("stitch_map_done")

    if stage_callback:
        stage_callback("generate_dead_mask_start")
    dead_heat = build_dead_weight_map(stitch_bounds)
    if dead_heat is None or not os.path.exists(DEAD_HEATMAP_PATH):
        raise FileNotFoundError(f"Dead-tree heatmap was not generated: {DEAD_HEATMAP_PATH}")
    if stage_callback:
        stage_callback("generate_dead_mask_done")

    if stage_callback:
        stage_callback("overlay_render_start")
    stitched = cv2.imread(MAP_OUTPUT_PATH)
    if stitched is None:
        raise FileNotFoundError(f"Cannot read stitched map image: {MAP_OUTPUT_PATH}")
    overlay_dead_heat_on_map(
        stitched,
        dead_heat,
        DEAD_OVERLAY_OPACITY,
        DEAD_OVERLAY_COLOR_BGR,
        MAP_DEAD_OVERLAY_PATH,
    )
    if not os.path.exists(MAP_DEAD_OVERLAY_PATH):
        raise FileNotFoundError(f"Overlay map was not generated: {MAP_DEAD_OVERLAY_PATH}")
    if stage_callback:
        stage_callback("overlay_render_done")
    return {
        "video_path": VIDEO_PATH,
        "frames_dir": FRAMES_DIR,
        "csv_path": CSV_PATH,
        "map_path": MAP_OUTPUT_PATH,
        "heatmap_path": DEAD_HEATMAP_PATH,
        "overlay_path": MAP_DEAD_OVERLAY_PATH,
    }


def record_video_data():
    os.makedirs(FRAMES_DIR, exist_ok=True)
    
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {VIDEO_PATH}")
    ret, old_frame = cap.read()
    if not ret: 
        cap.release()
        raise RuntimeError(f"Failed to read first frame from video: {VIDEO_PATH}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps): fps = 30.0 
    save_interval_seconds = SAVE_INTERVAL_SECONDS if SHOW_VIDEO else SAVE_INTERVAL_SECONDS_HEADLESS
    
    frames_per_interval = max(1, int(fps * save_interval_seconds))
    
    height, width = old_frame.shape[:2]
    mid_x = width // 2
    
    mask = np.full((height, width), 255, dtype=np.uint8)
    ignore_x_start = int(width * (1 - WATERMARK_WIDTH_PCT))
    ignore_y_end = int(height * WATERMARK_HEIGHT_PCT)
    mask[0:ignore_y_end, ignore_x_start:width] = 0

    old_gray = cv2.cvtColor(old_frame, cv2.COLOR_BGR2GRAY)
    p0 = cv2.goodFeaturesToTrack(old_gray, mask=mask, **feature_params)

    frame_counter = 0
    last_saved_frame_id = 0
    acc_dx, acc_dy = 0.0, 0.0

    with open(CSV_PATH, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frame_id', 'prev_frame_id', 'movement', 'avg_velocity_px_s', 'dx_total', 'dy_total'])

        cv2.imwrite(os.path.join(FRAMES_DIR, f"frame_{frame_counter}.jpg"), old_frame)
        writer.writerow([frame_counter, last_saved_frame_id, "START", 0.0, 0.0, 0.0])

        while True:
            ret, frame = cap.read()
            if not ret: break
            
            clean_frame = frame.copy() if SHOW_VIDEO else frame
            
            frame_counter += 1
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            avg_dx, avg_dy = 0, 0

            if p0 is not None:
                p1, st, err = cv2.calcOpticalFlowPyrLK(old_gray, frame_gray, p0, None, **lk_params)

                if p1 is not None:
                    good_new = p1[st == 1]
                    good_old = p0[st == 1]

                    if len(good_new) > 2:
                        dxs = good_new[:, 0] - good_old[:, 0]
                        dys = good_new[:, 1] - good_old[:, 1]
                        
                        avg_dx = np.mean(dxs)
                        avg_dy = np.mean(dys)

                        acc_dx += avg_dx
                        acc_dy += avg_dy

                        if SHOW_VIDEO:
                            for i, (new, old) in enumerate(zip(good_new, good_old)):
                                a, b = new.ravel()
                                cv2.circle(frame, (int(a), int(b)), 3, (0, 255, 0), -1)

            if frame_counter % frames_per_interval == 0:
                displacement_interval = np.sqrt(acc_dx**2 + acc_dy**2)
                
                velocity_px_s = displacement_interval / save_interval_seconds 

                movement_str = ""
                threshold = frames_per_interval * 0.3 
                
                if acc_dx > threshold: movement_str += "LEFT "
                elif acc_dx < -threshold: movement_str += "RIGHT "

                if acc_dy > threshold: movement_str += "UP "
                elif acc_dy < -threshold: movement_str += "DOWN "
                
                if not movement_str.strip():
                    movement_str = "STATIONARY"

                img_name = f"frame_{frame_counter}.jpg"
                cv2.imwrite(os.path.join(FRAMES_DIR, img_name), clean_frame)

                writer.writerow([frame_counter, last_saved_frame_id, movement_str.strip(), 
                                 round(velocity_px_s, 2), round(acc_dx, 2), round(acc_dy, 2)])
                
                last_saved_frame_id = frame_counter
                acc_dx, acc_dy = 0.0, 0.0 

            if SHOW_VIDEO:
                cv2.imshow('Recording & Analyzing Flow.', frame)
            old_gray = frame_gray.copy()
            p0 = cv2.goodFeaturesToTrack(old_gray, mask=mask, **feature_params)

            if SHOW_VIDEO and cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    if SHOW_VIDEO:
        cv2.destroyAllWindows()
    print(f"Data recording complete. Frames saved to /{FRAMES_DIR} and data to {CSV_PATH}")


def stitch_map_from_csv():
    """Reads the CSV and stitches the saved frames into a unified map based on velocity/movement.

    Returns crop box (x, y, w, h) in full canvas coordinates, or (0, 0, canvas_size, canvas_size)
    if no contours; None if CSV missing.
    """
    if not os.path.exists(CSV_PATH):
        print(f"Cannot find {CSV_PATH}. Run recording first.")
        return None

    print("Stitching map..")
    
    canvas_size = 8000 
    canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
    
    current_x = canvas_size // 2
    current_y = canvas_size // 2

    with open(CSV_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            frame_id = row['frame_id']
            dx_total = float(row['dx_total'])
            dy_total = float(row['dy_total'])
            
            current_x -= dx_total
            current_y -= dy_total
            
            img_path = os.path.join(FRAMES_DIR, f"frame_{frame_id}.jpg")
            img = cv2.imread(img_path)
            if img is None: continue

            h, w = img.shape[:2]
            
            x_start, y_start = int(current_x - w/2), int(current_y - h/2)
            
            y1, y2 = max(0, y_start), min(canvas.shape[0], y_start + h)
            x1, x2 = max(0, x_start), min(canvas.shape[1], x_start + w)

            img_y1 = y1 - y_start
            img_y2 = img_y1 + (y2 - y1)
            img_x1 = x1 - x_start
            img_x2 = img_x1 + (x2 - x1)

            if y1 < y2 and x1 < x2:
                canvas[y1:y2, x1:x2] = img[img_y1:img_y2, img_x1:img_x2]

    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        x, y, w, h = cv2.boundingRect(np.vstack(contours))
        cropped_canvas = canvas[y:y+h, x:x+w]
        cv2.imwrite(MAP_OUTPUT_PATH, cropped_canvas)
        print(f"Map successfully stitched and cropped! Saved as {MAP_OUTPUT_PATH}")
        return (x, y, w, h)
    cv2.imwrite(MAP_OUTPUT_PATH, canvas)
    print(f"Map successfully stitched! Saved as {MAP_OUTPUT_PATH}")
    return (0, 0, canvas_size, canvas_size)


def build_dead_weight_map(crop_bounds):
    """Accumulate per-frame weighted dead heat using the same integer placement as stitch_map_from_csv."""
    if crop_bounds is None:
        print("Skipping dead heatmap: no crop bounds (stitch may have failed).")
        return None
    if not os.path.exists(CSV_PATH):
        print("Skipping dead heatmap: CSV missing.")
        return None

    print("Building dead-tree heatmap..")
    canvas_size = 8000
    dead_canvas = np.zeros((canvas_size, canvas_size), dtype=np.float32)
    current_x = canvas_size // 2
    current_y = canvas_size // 2

    with open(CSV_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            frame_id = row['frame_id']
            dx_total = float(row['dx_total'])
            dy_total = float(row['dy_total'])
            current_x -= dx_total
            current_y -= dy_total

            img_path = os.path.join(FRAMES_DIR, f"frame_{frame_id}.jpg")
            img = cv2.imread(img_path)
            if img is None:
                continue
            heat = image_preprocessing.compute_weighted_dead_mask(img)
            if heat is None:
                continue
            heat_f = heat.astype(np.float32) / 255.0

            h, w = heat_f.shape[:2]
            x_start, y_start = int(current_x - w / 2), int(current_y - h / 2)
            y1, y2 = max(0, y_start), min(canvas_size, y_start + h)
            x1, x2 = max(0, x_start), min(canvas_size, x_start + w)
            img_y1 = y1 - y_start
            img_y2 = img_y1 + (y2 - y1)
            img_x1 = x1 - x_start
            img_x2 = img_x1 + (x2 - x1)
            if y1 < y2 and x1 < x2:
                patch = heat_f[img_y1:img_y2, img_x1:img_x2]
                dest = dead_canvas[y1:y2, x1:x2]
                np.maximum(dest, patch, out=dest)

    x, y, w, h = crop_bounds
    cropped = dead_canvas[y : y + h, x : x + w]
    heat_u8 = np.clip(cropped * 255.0, 0, 255).astype(np.uint8)
    cv2.imwrite(DEAD_HEATMAP_PATH, heat_u8)
    print(f"Dead heatmap saved as {DEAD_HEATMAP_PATH}")
    return cropped


def overlay_dead_heat_on_map(stitched_bgr, heat_cropped, opacity, color_bgr, out_path):
    """Blend color tint using per-pixel strength heat_cropped in [0,1] or uint8."""
    if stitched_bgr is None or heat_cropped is None:
        return
    h, w = stitched_bgr.shape[:2]
    if heat_cropped.shape[:2] != (h, w):
        heat_cropped = cv2.resize(heat_cropped, (w, h), interpolation=cv2.INTER_LINEAR)
    if heat_cropped.dtype != np.float32:
        a = heat_cropped.astype(np.float32) / 255.0
    else:
        a = np.clip(heat_cropped, 0.0, 1.0)
    alpha = (opacity * a[..., np.newaxis]).astype(np.float32)
    base = stitched_bgr.astype(np.float32)
    tint = np.array(color_bgr, dtype=np.float32).reshape(1, 1, 3)
    out = base * (1.0 - alpha) + tint * alpha
    out = np.clip(out, 0, 255).astype(np.uint8)
    cv2.imwrite(out_path, out)
    print(f"Dead overlay map saved as {out_path}")


if __name__ == "__main__":
    run_pipeline(
        video_path=VIDEO_PATH,
        output_dir=".",
        show_video=SHOW_VIDEO,
        save_interval_seconds=SAVE_INTERVAL_SECONDS,
        save_interval_seconds_headless=SAVE_INTERVAL_SECONDS_HEADLESS,
        dead_overlay_opacity=DEAD_OVERLAY_OPACITY,
        dead_overlay_color_bgr=DEAD_OVERLAY_COLOR_BGR,
    )