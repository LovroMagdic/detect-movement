import cv2
import numpy as np
import matplotlib.pyplot as plt
import os
import time

# --- OPTIMIZED GLOBAL PARAMETERS ---
SIZE = 32
RESIZE_DIM = (32, 32)

# Weights (M1 and M4 removed as per optimization)
WEIGHT_1 = 0.0  # find_and_plot_contours
WEIGHT_2 = 0.55 # analyze_texture_and_saturation (M2)
WEIGHT_3 = 0.45 # detect_dead_color_foliage (M3)
WEIGHT_4 = 0.0  # detect_edge_density

# Thresholding values
FINAL_MASK_THRESH = 95  # Optimized from training
THRESH_VAL = 119        # Using Texture Threshold for alignment
THRESH_MAX = 255

# Color parameters (M3)
GREEN_THRESH = 27       # Optimized
LOWER_DEAD = np.array([0, 0, 50])  # Optimized S_min
UPPER_DEAD = np.array([180, 60, 220])

# Texture parameters (M2)
TEXTURE_MULT = 1.1      # Optimized
TEXTURE_THRESH = 119    # Optimized

LAST_FINAL_PAIRS = []
SIMILARITY_THRESHOLD = 0

# --- CORE FUNCTIONS ---

def get_image_from_source(input_source, grayscale=False):
    if isinstance(input_source, str):
        if grayscale: return cv2.imread(input_source, cv2.IMREAD_GRAYSCALE)
        else: return cv2.imread(input_source)
    elif isinstance(input_source, np.ndarray):
        if grayscale:
            if len(input_source.shape) == 3: return cv2.cvtColor(input_source, cv2.COLOR_BGR2GRAY)
            return input_source
        else: return input_source
    return None

def detect_dead_color_foliage(image_source):
    img = get_image_from_source(image_source, grayscale=False)
    if img is None: return None
    img = cv2.resize(img, RESIZE_DIM)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray_mask = cv2.inRange(hsv, LOWER_DEAD, UPPER_DEAD)
    
    b, g, r = cv2.split(img.astype("float"))
    exg = 2*g - r - b
    
    _, green_mask = cv2.threshold(exg, GREEN_THRESH, 255, cv2.THRESH_BINARY)
    not_green_mask = cv2.bitwise_not(green_mask.astype(np.uint8))
    
    dead_mask = cv2.bitwise_and(gray_mask, not_green_mask)
    kernel = np.ones((3,3), np.uint8)
    dead_mask = cv2.morphologyEx(dead_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return dead_mask

def find_and_plot_contours(image_source):
    gray_img = get_image_from_source(image_source, grayscale=True)
    if gray_img is None: return None
    gray_img = cv2.resize(gray_img, RESIZE_DIM, interpolation=cv2.INTER_AREA)
    _, binary_img = cv2.threshold(gray_img, THRESH_VAL, THRESH_MAX, cv2.THRESH_BINARY)
    return binary_img

def analyze_texture_and_saturation(image_source):
    img = get_image_from_source(image_source, grayscale=False)
    if img is None: return None
    img = cv2.resize(img, RESIZE_DIM)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation_inverted = 255 - hsv[:, :, 1]
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k_size = 3
    blur = cv2.blur(gray, (k_size, k_size))
    blur_sq = cv2.blur(gray**2, (k_size, k_size))
    variance = blur_sq - blur**2
    texture_map = np.clip(np.sqrt(np.abs(variance)) * TEXTURE_MULT, 0, 255).astype(np.uint8)
    
    combined_feature = cv2.addWeighted(saturation_inverted, 0.5, texture_map, 0.5, 0)
    _, binary_mask = cv2.threshold(combined_feature, TEXTURE_THRESH, 255, cv2.THRESH_BINARY)
    return binary_mask

def detect_edge_density(image_source):
    img = get_image_from_source(image_source, grayscale=True)
    if img is None: return None
    img = cv2.resize(img, RESIZE_DIM)
    edges = cv2.Canny(img, 50, 150)
    density_map = cv2.GaussianBlur(edges, (9, 9), 0)
    _, binary_edge_mask = cv2.threshold(density_map, 40, 255, cv2.THRESH_BINARY)
    return binary_edge_mask

# --- GEOMETRY HELPERS ---

def expand_rect(rect, img_w, img_h, scale=1.2):
    x, y, w, h = rect
    center_x, center_y = x + w / 2, y + h / 2
    new_w, new_h = w * scale, h * scale
    new_x, new_y = center_x - new_w / 2, center_y - new_h / 2
    final_x, final_y = int(max(0, new_x)), int(max(0, new_y))
    final_w, final_h = int(min(img_w - final_x, new_w)), int(min(img_h - final_y, new_h))
    return (final_x, final_y, final_w, final_h)

def is_inside(inner, outer):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (ix >= ox) and (iy >= oy) and (ix + iw <= ox + ow) and (iy + ih <= oy + oh)

def filter_rect_pairs(pairs):
    if not pairs: return []
    pairs.sort(key=lambda p: p['expanded'][2] * p['expanded'][3], reverse=True)
    kept_pairs = []
    for current in pairs:
        is_nested = False
        current_exp = current['expanded']
        for kept in kept_pairs:
            kept_exp = kept['expanded']
            if is_inside(current_exp, kept_exp):
                is_nested = True
                break
        if not is_nested: kept_pairs.append(current)
    return kept_pairs

def is_similar(rect_new, rect_prev, threshold):
    nx, ny, nw, nh = rect_new
    px, py, pw, ph = rect_prev
    distance = np.sqrt((nx - px)**2 + (ny - py)**2)
    return distance < threshold


def reset_detection_state():
    global LAST_FINAL_PAIRS
    LAST_FINAL_PAIRS = []


def _combine_weighted_masks_small(image_bgr):
    """Returns weighted combination at RESIZE_DIM (uint8), or None if input invalid."""
    if image_bgr is None:
        return None
    zw = np.zeros((RESIZE_DIM[1], RESIZE_DIM[0]), dtype=np.uint8)
    m1 = find_and_plot_contours(image_bgr)
    m2 = analyze_texture_and_saturation(image_bgr)
    m3 = detect_dead_color_foliage(image_bgr)
    m4 = detect_edge_density(image_bgr)
    m1 = m1 if m1 is not None else zw
    m2 = m2 if m2 is not None else zw
    m3 = m3 if m3 is not None else zw
    m4 = m4 if m4 is not None else zw
    final_weighted = (
        m1.astype(np.float32) * WEIGHT_1
        + m2.astype(np.float32) * WEIGHT_2
        + m3.astype(np.float32) * WEIGHT_3
        + m4.astype(np.float32) * WEIGHT_4
    )
    return np.clip(final_weighted, 0, 255).astype(np.uint8)


def compute_weighted_dead_mask(image_bgr):
    """Full-resolution weighted dead-tree heatmap (0–255), before FINAL_MASK_THRESH binarization."""
    if image_bgr is None:
        return None
    orig_h, orig_w = image_bgr.shape[:2]
    small = _combine_weighted_masks_small(image_bgr)
    if small is None:
        return None
    return cv2.resize(small, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)


# --- PROCESSING LOOP ---

def process_frame(frame):
    global LAST_FINAL_PAIRS
    if frame is None: return None
    orig_h, orig_w = frame.shape[:2]
    
    m1 = find_and_plot_contours(frame)
    m2 = analyze_texture_and_saturation(frame)
    m3 = detect_dead_color_foliage(frame)
    m4 = detect_edge_density(frame)
    final_weighted = _combine_weighted_masks_small(frame)
    if final_weighted is None:
        return None
    
    _, final_binary_mask = cv2.threshold(final_weighted, FINAL_MASK_THRESH, 255, cv2.THRESH_BINARY)

    # Contour detection and bounding box expansion
    contours, _ = cv2.findContours(final_binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scale_x, scale_y = orig_w / SIZE, orig_h / SIZE
    
    current_candidates = []
    for cnt in contours:
        if cv2.contourArea(cnt) < 5: continue
        cnt_f = cnt.astype(np.float32)
        cnt_f[:, 0, 0] *= scale_x
        cnt_f[:, 0, 1] *= scale_y
        scaled_cnt = cnt_f.astype(np.int32)
        tight = cv2.boundingRect(scaled_cnt)
        exp = expand_rect(tight, orig_w, orig_h, scale=1.2)
        current_candidates.append({'expanded': exp})

    current_final_pairs = filter_rect_pairs(current_candidates)

    # Temporal smoothing logic
    if not LAST_FINAL_PAIRS:
        LAST_FINAL_PAIRS = current_final_pairs
    else:
        updated_pairs = []
        for cur in current_final_pairs:
            matched = False
            for prev in LAST_FINAL_PAIRS:
                if is_similar(cur['expanded'], prev['expanded'], SIMILARITY_THRESHOLD):
                    updated_pairs.append(prev)
                    matched = True
                    break
            if not matched:
                updated_pairs.append(cur)
        LAST_FINAL_PAIRS = updated_pairs

    # Create visual output
    view_raw = frame.copy()
    view_expanded = frame.copy()
    for item in LAST_FINAL_PAIRS:
        ex, ey, ew, eh = item['expanded']
        cv2.rectangle(view_expanded, (ex, ey), (ex + ew, ey + eh), (0, 0, 255), 2)

    def prep(m): return cv2.cvtColor(cv2.resize(m, (orig_w, orig_h)), cv2.COLOR_GRAY2BGR)
    vm1, vm2, vm3, vm4 = prep(m1), prep(m2), prep(m3), prep(m4)
    v_final_mask = prep(final_binary_mask)

    font, color, thick = cv2.FONT_HERSHEY_SIMPLEX, (255, 255, 255), 2
    cv2.putText(vm1, "M1: Threshold (W:0)", (20, 40), font, 0.8, color, thick)
    cv2.putText(vm2, f"M2: Texture (W:{WEIGHT_2})", (20, 40), font, 0.8, color, thick)
    cv2.putText(vm3, f"M3: Color (W:{WEIGHT_3})", (20, 40), font, 0.8, color, thick)
    cv2.putText(vm4, "M4: Edges (W:0)", (20, 40), font, 0.8, color, thick)
    cv2.putText(view_raw, "Raw Video", (20, 40), font, 0.8, color, thick)
    cv2.putText(v_final_mask, "Weighted Mask", (20, 40), font, 0.8, (0, 255, 0), thick)
    cv2.putText(view_expanded, "Detections", (20, 40), font, 0.8, (0, 0, 255), thick)

    # Build the 2-row dashboard
    target_w = 400
    target_h = int(target_w * (orig_h / orig_w))
    def rz(img): return cv2.resize(img, (target_w, target_h))

    row1 = np.hstack((rz(vm1), rz(vm2), rz(vm3), rz(vm4)))
    
    r1_h, r1_w = row1.shape[:2]
    p_w_r2 = r1_w // 3
    
    p1_r2 = cv2.resize(view_raw, (p_w_r2, target_h))
    p2_r2 = cv2.resize(v_final_mask, (p_w_r2, target_h))
    p3_r2 = cv2.resize(view_expanded, (r1_w - (p_w_r2 * 2), target_h))
    
    row2 = np.hstack((p1_r2, p2_r2, p3_r2))
    
    return np.vstack((row1, row2))