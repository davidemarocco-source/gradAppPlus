import cv2
import numpy as np
import json

def order_points(pts):
    """
    Rearrange coordinates to order: top-left, top-right, bottom-right, bottom-left
    """
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # Top-left
    rect[2] = pts[np.argmax(s)] # Bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # Top-right
    rect[3] = pts[np.argmax(diff)] # Bottom-left

    return rect

def four_point_transform(image, pts):
    """
    Apply perspective transform to obtain a top-down view of the image
    """
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    # Compute width of new image
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))

    # Compute height of new image
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))

    # Destination points
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")

    # Compute perspective matrix and warp
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

    return warped

def enhance_image(image):
    """
    Apply CLAHE and other contrast enhancements to handle shadows/lighting.
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return enhanced

def apply_bw_filter(image):
    """
    Applies a high-contrast B&W filter. 
    Uses CLAHE + soft thresholding to make markers/bubbles pop without losing all detail.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # 1. CLAHE for local contrast
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    
    # 2. Linear Contrast Stretch
    # Map [min, max] to [0, 255]
    enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
    
    # 3. Soft Binary-ish look (Sigmoid-like curve)
    # This makes whites whiter and blacks blacker but keeps some gray for the engine
    lookUpTable = np.empty((1,256), np.uint8)
    for i in range(256):
        # Push values < 100 towards 0, > 150 towards 255
        if i < 110:
            lookUpTable[0,i] = max(0, i - 40)
        elif i > 145:
            lookUpTable[0,i] = min(255, i + 40)
        else:
            lookUpTable[0,i] = i
    
    enhanced = cv2.LUT(enhanced, lookUpTable)
    
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

def find_marker_squares(image):
    """
    Finds the 4 black fiducial markers.
    Tries multiple thresholding strategies for maximum robustness.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    def get_markers_from_thresh(t_img):
        cnts = cv2.findContours(t_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        
        found = []
        img_area = image.shape[0] * image.shape[1]
        
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)
            (x, y, w, h) = cv2.boundingRect(approx)
            ar = w / float(h)
            area = cv2.contourArea(c)
            extent = area / float(w * h) if w * h > 0 else 0
            
            # Markers are squares: len=4, ar~1, extent~1
            if len(approx) == 4 and 0.6 <= ar <= 1.4 and extent > 0.6:
                # Area between 0.03% and 3% of image
                if area > (img_area * 0.0003) and area < (img_area * 0.03):
                    M = cv2.moments(c)
                    if M["m00"] != 0:
                        cX = int(M["m10"] / M["m00"])
                        cY = int(M["m01"] / M["m00"])
                        found.append((area, [cX, cY]))
        return found

    # Strategy 1: Adaptive (Good for camera & shadows)
    # We use a larger block size (21) for better stability
    thresh_adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5)
    markers = get_markers_from_thresh(thresh_adaptive)
    
    # Strategy 2: Global Binary (Good for high-contrast/pre-processed)
    if len(markers) < 4:
        _, thresh_global = cv2.threshold(blurred, 120, 255, cv2.THRESH_BINARY_INV)
        markers = get_markers_from_thresh(thresh_global)
        
    # Strategy 3: Otsu
    if len(markers) < 4:
        _, thresh_otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        markers = get_markers_from_thresh(thresh_otsu)

    if len(markers) < 4:
        return None
        
    # Sort by area descending and take top 4
    markers.sort(key=lambda x: x[0], reverse=True)
    top_markers = [m[1] for m in markers[:4]]
        
    return order_points(np.array(top_markers))

def sample_bubble_hybrid(warped_gray, ideal_px, ideal_py, search_r=6, sample_r=5):
    """
    Seeks the darkest point within search_r of (ideal_px, ideal_py).
    """
    h, w = warped_gray.shape
    y_min, y_max = max(0, ideal_py - search_r), min(h, ideal_py + search_r + 1)
    x_min, x_max = max(0, ideal_px - search_r), min(w, ideal_px + search_r + 1)
    
    roi = warped_gray[y_min:y_max, x_min:x_max]
    if roi.size > 0:
        min_loc = np.unravel_index(np.argmin(roi, axis=None), roi.shape)
        best_py = y_min + min_loc[0]
        best_px = x_min + min_loc[1]
    else:
        best_px, best_py = ideal_px, ideal_py
                    
    sy_min, sy_max = max(0, best_py - sample_r), min(h, best_py + sample_r + 1)
    sx_min, sx_max = max(0, best_px - sample_r), min(w, best_px + sample_r + 1)
    
    final_avg = np.mean(warped_gray[sy_min:sy_max, sx_min:sx_max])
    return final_avg, (best_px, best_py)

def process_exam(image_path, num_questions=20, mcq_choices=5, question_data=None):
    """
    Full pipeline: Marker detection -> Warping -> Student ID -> Answers.
    """
    image = cv2.imread(image_path)
    if image is None:
        return {"success": False, "error": "Could not read image"}
        
    h, w = image.shape[:2]
    max_dim = 1200
    scale = 1.0
    if h > max_dim or w > max_dim:
        scale = max_dim / float(max(h, w))
        small_img = cv2.resize(image, (int(w * scale), int(h * scale)))
    else:
        small_img = image

    small_corners = find_marker_squares(small_img)
    if small_corners is None:
        # Debug image: Show edges
        debug = cv2.Canny(cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY), 50, 150)
        return {
            "success": False, 
            "error": "Could not find corner squares. Try better lighting or hold the camera closer.",
            "debug_image": debug
        }
        
    corners = small_corners / scale
        
    if num_questions <= 12: num_cols = 1
    elif num_questions <= 24: num_cols = 2
    else: num_cols = 3
    
    questions_per_col = (num_questions + num_cols - 1) // num_cols
    max_y_content = 115 + (questions_per_col * 10)
    bottom_y_mm = max_y_content + 10
    
    active_w_mm = 170 
    active_h_mm = (bottom_y_mm + 5) - 20
    
    w_target = 1000
    h_target = int(w_target * (active_h_mm / active_w_mm))
    
    dst = np.array([
        [0, 0],
        [w_target - 1, 0],
        [w_target - 1, h_target - 1],
        [0, h_target - 1]], dtype="float32")
        
    M = cv2.getPerspectiveTransform(corners.astype("float32"), dst)
    warped = cv2.warpPerspective(image, M, (w_target, h_target))
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) 
            
    def to_px(mm_x, mm_y):
        return int(((mm_x - 20) / active_w_mm) * w_target), int(((mm_y - 20) / active_h_mm) * h_target)
        
    all_bubble_centers = []
    
    # --- 1. Process Student ID ---
    id_start_x = 140
    id_start_y = 30 
    id_digits = []
    for c in range(3):
        col_x = id_start_x + (c * 10) + 12
        intensities = []
        found_centers = []
        for r in range(10):
            bubble_y = id_start_y + (r * 8)
            px, py = to_px(col_x + 2.75, bubble_y + 2.75)
            intensity, center = sample_bubble_hybrid(warped_gray, px, py, search_r=5, sample_r=5)
            intensities.append(intensity)
            found_centers.append(center)
        min_idx = np.argmin(intensities)
        if intensities[min_idx] < (np.mean(intensities) * 0.90):
            id_digits.append(str(min_idx))
            all_bubble_centers.append(found_centers[min_idx])
        else:
            id_digits.append("?")
            
    student_id_str = "".join(id_digits)
    omr_id = int(student_id_str) if "?" not in student_id_str else None
    
    # --- 1b. Process Version ---
    v_start_x = 110
    v_start_y = 40 
    v_intensities = []
    v_centers = []
    for r in range(5):
        bubble_y = v_start_y + (r * 8)
        px, py = to_px(v_start_x + 7 + 2.75, bubble_y + 2.75)
        intensity, center = sample_bubble_hybrid(warped_gray, px, py, search_r=5, sample_r=5)
        v_intensities.append(intensity)
        v_centers.append(center)
    v_min_idx = np.argmin(v_intensities)
    version_idx = v_min_idx if v_intensities[v_min_idx] < (np.mean(v_intensities) * 0.90) else None
    if version_idx is not None:
        all_bubble_centers.append(v_centers[version_idx])
    
    # --- 2. Process Answer Grid ---
    grid_width_mm = num_cols * (80 if num_cols==1 else (75 if num_cols==2 else 60))
    x_base_start_mm = (210 - grid_width_mm) / 2
    start_y_mm = 115 
    row_height_mm = 10
    bubble_spacing_mm = 9
    final_answers = {}
    
    for c in range(num_cols):
        col_x_start = x_base_start_mm + (c * (80 if num_cols==1 else (75 if num_cols==2 else 60)))
        qs_in_this_col = min(questions_per_col, num_questions - (c * questions_per_col))
        for q_idx in range(qs_in_this_col):
            abs_q_num = (c * questions_per_col) + q_idx + 1
            if question_data and str(abs_q_num) in question_data:
                q_info = question_data[str(abs_q_num)]
                if isinstance(q_info, dict) and q_info.get("type") == "Numeric":
                    continue
            
            row_y_mm = start_y_mm + (q_idx * row_height_mm)
            by_mm = row_y_mm + (10 - 6.5) / 2
            row_intensities = []
            found_centers = []
            for j in range(mcq_choices):
                bx_mm = col_x_start + 15 + (j * bubble_spacing_mm)
                px, py = to_px(bx_mm + 3.25, by_mm + 3.25)
                intensity, center = sample_bubble_hybrid(warped_gray, px, py, search_r=5, sample_r=6)
                row_intensities.append(intensity)
                found_centers.append(center)
            min_idx = np.argmin(row_intensities)
            if row_intensities[min_idx] < (np.mean(row_intensities) * 0.92):
                final_answers[abs_q_num] = min_idx
                all_bubble_centers.append(found_centers[min_idx])
            
    # Draw results
    for (cx, cy) in all_bubble_centers:
        cv2.circle(warped, (cx, cy), 14, (0, 255, 0), 2)
        cv2.circle(warped, (cx, cy), 4, (0, 255, 0), -1)
            
    return {
        "success": True,
        "warped_image": warped,
        "debug_image": None,
        "omr_id": omr_id,
        "version_idx": version_idx,
        "answers": final_answers
    }
