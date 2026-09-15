import cv2
import numpy as np
import os
import csv
import time

import dead_tree_model
import forest_overlay
from web_image import cap_image_for_web, heatmap_to_web_bgr, prepare_web_jpeg

VIDEO_PATH = r"C:\Users\Lovro\Desktop\diplomski_rad\detect_motion\video5_XG9GWA4Q.mp4"
OUTPUT_DIR = "final_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MOVE_THRESHOLD_PCT = 0.1
CSV_PATH = os.path.join(OUTPUT_DIR, 'movement_data.csv')
FRAMES_DIR = os.path.join(OUTPUT_DIR, 'captured_frames')

SHOW_VIDEO = False
OVERLAY_OPACITY = 0.5

feature_params = dict(maxCorners=100, qualityLevel=0.5, minDistance=20, blockSize=7)
lk_params = dict(winSize=(21, 21), maxLevel=3, 
                 criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))

def record_movement_data(roi=None):
    os.makedirs(FRAMES_DIR, exist_ok=True)
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"Error: Could not open video {VIDEO_PATH}")
        return False

    ret, old_frame = cap.read()
    if not ret: return False

    if roi is not None:
        rx, ry, rw, rh = [int(v) for v in roi]
    else:
        sel = cv2.selectROI("SELECT WATERMARK", old_frame, fromCenter=False)
        cv2.destroyWindow("SELECT WATERMARK")
        rx, ry, rw, rh = [int(v) for v in sel]

    height, width = old_frame.shape[:2]
    move_threshold_px = width * MOVE_THRESHOLD_PCT

    mask = np.full((height, width), 255, dtype=np.uint8)
    if rw > 0 and rh > 0: 
        mask[ry:ry+rh, rx:rx+rw] = 0

    old_gray = cv2.cvtColor(old_frame, cv2.COLOR_BGR2GRAY)
    p0 = cv2.goodFeaturesToTrack(old_gray, mask=mask, **feature_params)

    frame_count = 0
    acc_dx, acc_dy = 0.0, 0.0
    prev_time = time.time()

    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frame_id', 'dx_total', 'dy_total'])

        print("Processing video and capturing frames...")
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            frame_count += 1
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if p0 is not None:
                p1, st, err = cv2.calcOpticalFlowPyrLK(old_gray, frame_gray, p0, None, **lk_params)
                if p1 is not None:
                    good_new = p1[st == 1]; good_old = p0[st == 1]
                    if len(good_new) > 2:
                        dx = np.mean(good_new[:,0] - good_old[:,0])
                        dy = np.mean(good_new[:,1] - good_old[:,1])
                        acc_dx += dx; acc_dy += dy

            dist = np.sqrt(acc_dx**2 + acc_dy**2)
            if dist >= move_threshold_px:
                cv2.imwrite(os.path.join(FRAMES_DIR, f"{frame_count}.jpg"), frame)
                writer.writerow([frame_count, acc_dx, acc_dy])
                acc_dx, acc_dy = 0.0, 0.0

            if SHOW_VIDEO:
                if rw > 0: cv2.rectangle(frame, (rx, ry), (rx+rw, ry+rh), (0, 0, 255), 2)
                cv2.imshow('Recording Movement', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
            
            old_gray = frame_gray.copy()
            p0 = cv2.goodFeaturesToTrack(old_gray, mask=mask, **feature_params)

    cap.release()
    cv2.destroyAllWindows()
    return True

def stitch_dual_maps():
    if not os.path.exists(CSV_PATH): return None

    coords = []
    curr_x, curr_y = 0.0, 0.0
    with open(CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            curr_x -= float(row['dx_total']); curr_y -= float(row['dy_total'])
            coords.append((curr_x, curr_y, row['frame_id']))

    if not coords: return None

    first_img = cv2.imread(os.path.join(FRAMES_DIR, f"{coords[0][2]}.jpg"))
    fh, fw = first_img.shape[:2]

    all_x, all_y = [c[0] for c in coords], [c[1] for c in coords]
    min_x, min_y = min(all_x), min(all_y)
    max_x, max_y = max(all_x), max(all_y)

    canvas_w, canvas_h = int(max_x - min_x) + fw, int(max_y - min_y) + fh
    
    print(f"Creating Dual Discovery Canvases: {canvas_w}x{canvas_h}")
    visual_canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    heatmap_canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)

    for x, y, fid in coords:
        img = cv2.imread(os.path.join(FRAMES_DIR, f"{fid}.jpg"))
        if img is None: continue
        
        dead_mask = dead_tree_model.compute_dead_mask(img)
        
        sx, sy = int(x - min_x), int(y - min_y)
        
        v_roi = visual_canvas[sy:sy+fh, sx:sx+fw]
        v_is_empty = np.all(v_roi == 0, axis=-1)
        v_roi[v_is_empty] = img[v_is_empty]

        h_roi = heatmap_canvas[sy:sy+fh, sx:sx+fw]
        h_is_empty = (h_roi == 0)
        h_roi[h_is_empty] = dead_mask[h_is_empty]

    return visual_canvas, heatmap_canvas

def finalize_output(visual, heatmap):
    gray = cv2.cvtColor(visual, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: return
    
    tx, ty, tw, th = cv2.boundingRect(np.vstack(cnts))
    visual = visual[ty:ty+th, tx:tx+tw]
    heatmap = heatmap[ty:ty+th, tx:tx+tw]

    red_heatmap = np.zeros_like(visual)
    red_heatmap[:, :] = (0, 0, 255)
    
    colored_heat = cv2.bitwise_and(red_heatmap, red_heatmap, mask=heatmap)

    overlay = cv2.addWeighted(visual, 1.0, colored_heat, OVERLAY_OPACITY, 0)

    visual = cap_image_for_web(visual)
    heatmap = cap_image_for_web(heatmap)
    overlay = cap_image_for_web(overlay)
    heatmap_bgr = heatmap_to_web_bgr(heatmap)

    out_dir = OUTPUT_DIR
    with open(os.path.join(out_dir, "final_stitched_map.jpg"), "wb") as f:
        f.write(prepare_web_jpeg(visual))
    with open(os.path.join(out_dir, "dead_tree_heatmap.jpg"), "wb") as f:
        f.write(prepare_web_jpeg(heatmap_bgr))
    with open(os.path.join(out_dir, "final_overlay_result.jpg"), "wb") as f:
        f.write(prepare_web_jpeg(overlay))
    
    print(f"Pipeline Complete. Files saved in {OUTPUT_DIR}")
    
    if SHOW_VIDEO:
        cv2.namedWindow("Final Overlay", cv2.WINDOW_NORMAL)
        cv2.imshow("Final Overlay", overlay)
        cv2.waitKey(0)

def run_pipeline(
    video_path,
    output_dir,
    show_video=False,
    use_watermark_zone=False,
    watermark_x=None,
    watermark_y=None,
    watermark_width=None,
    watermark_height=None,
    stage_callback=None,
    **kwargs,
):
    global VIDEO_PATH, OUTPUT_DIR, CSV_PATH, FRAMES_DIR, SHOW_VIDEO

    VIDEO_PATH = video_path
    OUTPUT_DIR = output_dir
    CSV_PATH = os.path.join(OUTPUT_DIR, 'movement_data.csv')
    FRAMES_DIR = os.path.join(OUTPUT_DIR, 'captured_frames')
    SHOW_VIDEO = show_video

    roi = (0, 0, 0, 0)
    if (watermark_x is not None and watermark_y is not None
            and watermark_width is not None and watermark_width > 0
            and watermark_height is not None and watermark_height > 0):
        roi = (watermark_x, watermark_y, watermark_width, watermark_height)

    if stage_callback:
        stage_callback("extract_and_detect_start")
    if not record_movement_data(roi=roi):
        raise RuntimeError(f"record_movement_data failed for {video_path}")
    if stage_callback:
        stage_callback("extract_and_detect_done")

    if stage_callback:
        stage_callback("stitch_map_start")
    maps = stitch_dual_maps()
    if maps is None:
        raise RuntimeError("stitch_dual_maps returned no result")
    v_map, h_map = maps
    if stage_callback:
        stage_callback("stitch_map_done")

    if stage_callback:
        stage_callback("generate_dead_mask_start")
        stage_callback("generate_dead_mask_done")
        stage_callback("overlay_render_start")
    finalize_output(v_map, h_map)
    if stage_callback:
        stage_callback("overlay_render_done")

    if stage_callback:
        stage_callback("forest_overlay_start")
    forest_overlay_path = forest_overlay.stitch_forest_overlay(
        frames_dir=FRAMES_DIR,
        csv_path=CSV_PATH,
        output_dir=OUTPUT_DIR,
    )
    if stage_callback:
        stage_callback("forest_overlay_done")

    return {
        "video_path": video_path,
        "frames_dir": FRAMES_DIR,
        "csv_path": CSV_PATH,
        "map_path": os.path.join(OUTPUT_DIR, "final_stitched_map.jpg"),
        "heatmap_path": os.path.join(OUTPUT_DIR, "dead_tree_heatmap.jpg"),
        "overlay_path": os.path.join(OUTPUT_DIR, "final_overlay_result.jpg"),
        "forest_overlay_path": forest_overlay_path or "",
    }


if __name__ == "__main__":
    if record_movement_data():
        v_map, h_map = stitch_dual_maps()
        if v_map is not None:
            finalize_output(v_map, h_map)
