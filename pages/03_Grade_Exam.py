import streamlit as st
import db_manager
import omr_engine
import cv2
import numpy as np
import json
from PIL import Image

st.set_page_config(page_title="Grade Exam", page_icon="📸")

st.title("📸 Grade Exam")

# 1. Select Exam
exams = db_manager.get_all_classes() 
# We need to select class first? Or just list all recent exams?
# Let's list all exams with their class names.
# Need a better DB query for that, but let's iterate.
all_classes = db_manager.get_all_classes()
if not all_classes:
    st.warning("No classes/exams found.")
    st.stop()

class_map = {c[1]: c[0] for c in all_classes}
selected_class_name = st.selectbox("Select Class", list(class_map.keys()))
selected_class_id = class_map[selected_class_name]

exams = db_manager.get_exams_by_class(selected_class_id)
if not exams:
    st.warning("No exams for this class.")
    st.stop()
    
# Filter: Hide individual versions from the main grading dropdown.
# Users should pick the "Master" or an independent exam.
# ex[3] is the parent_id
top_level_exams = [e for e in exams if e[3] is None or (isinstance(e[3], (float, int)) and np.isnan(float(e[3])))]

if not top_level_exams:
    st.warning("No masters or independent exams found.")
    st.stop()

exam_opts = {f"{e[1]} ({e[2]})": e[0] for e in top_level_exams}
selected_exam_label = st.selectbox("Select Exam to Grade", list(exam_opts.keys()))
selected_exam_id = exam_opts[selected_exam_label]

# Load Exam Details (Key)
exam_details = db_manager.get_exam_details(selected_exam_id)
# id, name, class_id, date, answer_key, mcq_choices, parent_id
master_id = exam_details[6]
is_version = master_id is not None

# If this is a master or a version, we might need to swap the key based on the scan
available_versions = []
if "(Master)" in exam_details[1] or is_version:
    pid = master_id if is_version else selected_exam_id
    available_versions = db_manager.get_exam_versions(pid)

answer_key = json.loads(exam_details[4]) 
mcq_choices = exam_details[5]

# 2. Privacy & Tips
with st.expander("ℹ️ Privacy & Mobile Scanning Tips"):
    st.info("""
    **Privacy Info**: Images are processed in real-time. They are temporarily stored only for the duration of the scan and are **not** saved permanently unless you click 'Save Grade' below.
    
    **Tips for Phone Scanning**:
    - **Align the Squares**: Ensure all 4 black squares in the corners are visible and not Cut off.
    - **Light is Key**: Avoid shadows. If possible, place the sheet on a flat surface in a well-lit room.
    - **Hold Parallel**: Try to hold your phone parallel to the paper, not at an angle.
    - **No Flash**: Flash often creates a glare on the paper that blinds the scanner.
    """)

# 3. Input Method
input_method = st.radio("Input Method", ["Upload Image", "Camera"])

image_file = None
if input_method == "Upload Image":
    image_file = st.file_uploader("Upload Scanned Sheet", type=['jpg', 'png', 'jpeg'])
else:
    image_file = st.camera_input("Take a picture of the sheet")

# --- Enhancement Settings ---
st.sidebar.header("Scanning Settings")
enable_bw = st.sidebar.toggle("B&W Enhancement", value=True, help="Applies a high-contrast filter to make paper whiter and ink blacker. Highly recommended for phone scans.")

# --- Main Processing ---
if image_file:
    # Convert to CV2
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    image = cv2.imdecode(file_bytes, 1)
    
    # Apply B&W enhancement if requested
    if enable_bw:
        image = omr_engine.apply_bw_filter(image)
    
    # st.image(image, caption="Original Image", channels="BGR", use_container_width=True)
    
    if st.button("🚀 Process & Grade", use_container_width=True):
        with st.spinner("Analyzing..."):
            temp_path = "temp_scan.jpg"
            cv2.imwrite(temp_path, image)
            
            # Determine layout question count (if master is empty, use first version's count)
            num_qs_layout = len(answer_key)
            if num_qs_layout == 0 and available_versions:
                v1_key = json.loads(available_versions[0][3])
                num_qs_layout = len(v1_key)
                
            result = omr_engine.process_exam(temp_path, num_questions=num_qs_layout, mcq_choices=mcq_choices, question_data=answer_key)
            
            st.session_state['scan_result'] = result
            st.session_state['manual_student_id'] = None # Reset manual override
            
            if result["success"]:
                st.success("Processing Complete!")
            else:
                st.error(f"Failed: {result['error']}")
                # Show debug image to help alignment
                if "debug_image" in result:
                    st.image(result["debug_image"], caption="Scanner View (Align the 4 corners)", use_container_width=True)

# --- Results Display (Persists after reruns) ---
if 'scan_result' in st.session_state and st.session_state['scan_result']:
    result = st.session_state['scan_result']
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.image(result["warped_image"], caption="Warped View", channels="BGR")
    
    with col2:
        omr_id = result.get("omr_id")
        version_idx = result.get("version_idx")
        version_letter = chr(65 + version_idx) if version_idx is not None else "?"
        
        st.write(f"**Detected OMR ID:** {omr_id}")
        st.write(f"**Detected Version:** {version_letter}")
        
        # --- Version Switching Logic ---
        current_answer_key = answer_key
        current_exam_id = selected_exam_id
        
        if available_versions and version_idx is not None:
            # Try to find the version matching the detected letter
            target_name_part = f"(Version {version_letter})"
            matched_version = None
            for v in available_versions:
                if target_name_part in v[1]:
                    matched_version = v
                    break
            
            if matched_version:
                st.info(f"Using key for: **{matched_version[1]}**")
                current_answer_key = json.loads(matched_version[3])
                current_exam_id = matched_version[0]
            else:
                st.warning(f"Could not find a specific exam record for Version {version_letter}. Using the currently selected exam.")
        elif available_versions and version_idx is None:
            st.warning("No version detected on sheet. Using the currently selected exam record.")
        
        student_id = None
        
        # 1. Try Auto-Match
        if omr_id is not None:
            student = db_manager.get_student_by_omr(selected_class_id, omr_id)
            if student:
                st.success(f"Matched Student:\n**{student[1]}**\n({student[2]})")
                student_id = student[0]
            else:
                st.error(f"Student with OMR ID {omr_id} not found in this class!")
        else:
            st.error("Could not read OMR ID.")

        # 2. Manual Override (If match failed or user wants to change)
        student_list = db_manager.get_students_by_class(selected_class_id)
        stu_opts = {f"{s[1]} (OMR: {s[3]})": s[0] for s in student_list}
        
        # Find index of current match if any
        current_idx = 0
        if student_id:
            for i, sid in enumerate(stu_opts.values()):
                if sid == student_id:
                    current_idx = i
                    break
        
        st.divider()
        sel_stu_label = st.selectbox("Assign to Student", list(stu_opts.keys()), index=current_idx)
        student_id = stu_opts[sel_stu_label]
            
        # 3. Grading Logic
        student_answers = result["answers"]
        score = 0
        total = 0
        graded_details = {}
        idx_to_char = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E"}
        
        for q_str, key_val in current_answer_key.items():
            q_idx = int(q_str)
            
            # Handle new format {"ans": "...", "type": "..."} vs old format "..."
            if isinstance(key_val, dict):
                proper_ans = key_val.get("ans")
                q_type = key_val.get("type", "MCQ")
            else:
                proper_ans = key_val
                q_type = "MCQ"
            
            stu_ans_idx = student_answers.get(q_idx)
            stu_ans_char = idx_to_char.get(stu_ans_idx, "?") if stu_ans_idx is not None else "N/A"
            
            if q_type == "Numeric":
                is_correct = False # Manual grading needed
                stu_ans_char = "Num"
            else:
                is_correct = (stu_ans_char == proper_ans)
                if is_correct:
                    score += 1
            
            graded_details[q_idx] = {
                "student": stu_ans_char,
                "correct": proper_ans,
                "is_correct": is_correct,
                "type": q_type
            }
            if q_type != "Numeric":
                total += 1
            
        st.metric("Score", f"{score} / {total}")
        
        if st.button("Save Grade"):
            # Use original student_id (either matched or selected from dropdown)
            db_manager.save_result(current_exam_id, student_id, score, graded_details, "scan.jpg")
            st.success("Saved to Database!")
            # Clear result after saving to prevent double submission
            st.session_state['scan_result'] = None
            st.rerun()

