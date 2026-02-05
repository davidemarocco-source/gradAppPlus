import cv2
import numpy as np

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

def find_document_corners(image):
    """
    Find the 4 corners of the document in the image.
    Tries multiple strategies for robust detection on mobile.
    Returns (corners, debug_image)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Strategy 1: Canny Edges
    edged = cv2.Canny(blurred, 75, 200)
    
    strategies = [
        ("Canny", edged),
        ("Otsu", cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]),
        ("Adaptive", cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2))
    ]
    
    best_approx = None
    
    for name, processed in strategies:
        cnts = cv2.findContours(processed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        
        if len(cnts) > 0:
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
            for c in cnts:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                
                if len(approx) == 4 and cv2.contourArea(c) > (image.shape[0] * image.shape[1] * 0.2):
                    return approx.reshape(4, 2), edged
                
                # Keep the largest 4-point contour even if it doesn't meet the area threshold yet
                if len(approx) == 4 and (best_approx is None or cv2.contourArea(c) > cv2.contourArea(best_approx)):
                    best_approx = approx
                    
    if best_approx is not None:
        return best_approx.reshape(4, 2), edged
                
    return None, edged

def pre_process_image(image):
    """
    Basic preprocessing pipeline
    """
    return enhance_image(image)

def sort_contours(cnts, method="left-to-right"):
    """
    Sort contours based on the provided method.
    """
    reverse = False
    i = 0
    if method == "right-to-left" or method == "bottom-to-top":
        reverse = True
    if method == "top-to-bottom" or method == "bottom-to-top":
        i = 1

    boundingBoxes = [cv2.boundingRect(c) for c in cnts]
    (cnts, boundingBoxes) = zip(*sorted(zip(cnts, boundingBoxes),
        key=lambda b: b[1][i], reverse=reverse))
        
    return (cnts, boundingBoxes)

def find_marker_squares(image):
    """
    Finds the 4 black fiducial markers (10mm squares).
    Returns the centers of the 4 markers in sorted order (TL, TR, BR, BL).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Use adaptive threshold to handle shadows
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    
    cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    
    markers = []
    img_area = image.shape[0] * image.shape[1]
    
    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        (x, y, w, h) = cv2.boundingRect(approx)
        ar = w / float(h)
        area = cv2.contourArea(c)
        
        # Extent: ratio of contour area to bounding box area (should be ~1.0 for a square)
        extent = area / float(w * h) if w * h > 0 else 0
        
        # Markers are roughly 10x10mm. On a typical 1080p scan (~300dpi), that's ~120px.
        # We look for solid squares that aren't too small or too large.
        if len(approx) == 4 and 0.8 <= ar <= 1.2 and extent > 0.8:
            if area > (img_area * 0.0005) and area < (img_area * 0.02):
                M = cv2.moments(c)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    markers.append([cX, cY])
                    
    if len(markers) < 4:
        return None
        
    # If more than 4, take the 4 most symmetric ones (largest area usually)
    if len(markers) > 4:
        markers = markers[:4] # Simplify for now
        
    return order_points(np.array(markers))

def sample_bubble_hybrid(warped_gray, ideal_px, ideal_py, search_r=6, sample_r=5):
    """
    Turbo Version: Uses NumPy slicing for speed.
    Seeks the darkest point within search_r of (ideal_px, ideal_py).
    """
    h, w = warped_gray.shape
    
    best_px, best_py = ideal_px, ideal_py
    min_val = 255
    
    # 1. Coordinate Seeking using NumPy slicing
    y_min, y_max = max(0, ideal_py - search_r), min(h, ideal_py + search_r + 1)
    x_min, x_max = max(0, ideal_px - search_r), min(w, ideal_px + search_r + 1)
    
    # Extract neighborhood
    roi = warped_gray[y_min:y_max, x_min:x_max]
    
    # Find min value location in ROI using numpy
    if roi.size > 0:
        min_loc = np.unravel_index(np.argmin(roi, axis=None), roi.shape)
        best_py = y_min + min_loc[0]
        best_px = x_min + min_loc[1]
                    
    # 2. Final sample: simple square/circular average using slice
    sy_min, sy_max = max(0, best_py - sample_r), min(h, best_py + sample_r + 1)
    sx_min, sx_max = max(0, best_px - sample_r), min(w, best_px + sample_r + 1)
    
    final_avg = np.mean(warped_gray[sy_min:sy_max, sx_min:sx_max])
    return final_avg, (best_px, best_py)

def get_answers_from_roi(roi, num_questions=5, choices=5):
    """
    Deprecated: Using coordinate-based sampling instead.
    """
    return {}

def process_exam(image_path, num_questions=20, mcq_choices=5, question_data=None):
    """
    Full pipeline: Marker detection -> Warping -> Student ID -> Answers.
    """
    image = cv2.imread(image_path)
    if image is None:
        return {"success": False, "error": "Could not read image"}
        
    # --- TURBO MODE: Downscale for faster marker detection ---
    h, w = image.shape[:2]
    max_dim = 1200
    scale = 1.0
    if h > max_dim or w > max_dim:
        scale = max_dim / float(max(h, w))
        small_img = cv2.resize(image, (int(w * scale), int(h * scale)))
    else:
        small_img = image

    # Find markers on small image
    small_corners = find_marker_squares(small_img)
    if small_corners is None:
        return {
            "success": False, 
            "error": "Could not find all 4 corner squares. Please ensure they are clearly visible in the camera view.",
            "debug_image": cv2.Canny(cv2.cvtColor(small_img, cv2.COLOR_BGR2GRAY), 75, 200)
        }
        
    # Scale corners back to original size
    corners = small_corners / scale
        
    # Calculate Sheet Top/Bottom bounds in MM - Sync with Generator
    if num_questions <= 12: num_cols = 1
    elif num_questions <= 24: num_cols = 2
    else: num_cols = 3
    
    questions_per_col = (num_questions + num_cols - 1) // num_cols
    max_y_content = 115 + (questions_per_col * 10)
    bottom_y_mm = max_y_content + 10
    
    # Use the marker box as the basis for warping
    active_w_mm = 170 # 190 - 20
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
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY) # One-time conversion
            
    def to_px(mm_x, mm_y):
        return int(((mm_x - 20) / active_w_mm) * w_target), int(((mm_y - 20) / active_h_mm) * h_target)
        
    all_bubble_centers = []
    
    # --- 1. Process Student ID (3 columns of digits 0-9) ---
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
        min_val = intensities[min_idx]
        avg_val = np.mean(intensities)
        
        if min_val < (avg_val * 0.88):
            id_digits.append(str(min_idx))
            all_bubble_centers.append(found_centers[min_idx])
        else:
            id_digits.append("?")
            
    student_id_str = "".join(id_digits)
    omr_id = int(student_id_str) if "?" not in student_id_str else None
    
    # --- 1b. Process Version (A-E) ---
    v_start_x = 110
    v_start_y = 30
    v_intensities = []
    v_centers = []
    for r in range(5):
        bubble_y = v_start_y + (r * 8)
        px, py = to_px(v_start_x + 7 + 2.75, bubble_y + 2.75)
        intensity, center = sample_bubble_hybrid(warped_gray, px, py, search_r=5, sample_r=5)
        v_intensities.append(intensity)
        v_centers.append(center)
        
    v_min_idx = np.argmin(v_intensities)
    v_min_val = v_intensities[v_min_idx]
    v_avg_val = np.mean(v_intensities)
    
    version_idx = None
    if v_min_val < (v_avg_val * 0.88):
        version_idx = v_min_idx
        all_bubble_centers.append(v_centers[v_min_idx])
    
    # --- 2. Process Answer Grid ---
    questions_per_col = (num_questions + num_cols - 1) // num_cols
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
            
            # Skip numeric questions for bubble detection
            q_data = question_data.get(str(abs_q_num), {}) if question_data else {}
            q_type = q_data.get("type", "MCQ") if isinstance(q_data, dict) else "MCQ"
            if q_type == "Numeric":
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
            min_val = row_intensities[min_idx]
            avg_val = np.mean(row_intensities)
            
            if min_val < (avg_val * 0.90):
                final_answers[abs_q_num] = min_idx
                all_bubble_centers.append(found_centers[min_idx])
            
    # DRAW VISUAL BUBBLES
    for (cx, cy) in all_bubble_centers:
        cv2.circle(warped, (cx, cy), 14, (0, 255, 0), 2) # Outer ring
        cv2.circle(warped, (cx, cy), 4, (0, 255, 0), -1) # Center dot
            
    return {
        "success": True,
        "warped_image": warped,
        "debug_image": None,
        "omr_id": omr_id,
        "version_idx": version_idx, # 0=A, 1=B, etc.
        "answers": final_answers
    }
