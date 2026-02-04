import streamlit as st
from fpdf import FPDF
import base64
import db_manager
import json

st.set_page_config(page_title="Generate Sheet", page_icon="🖨️")
st.title("🖨️ Answer Sheet Generator")

# --- Exam Selection Logic ---
classes = db_manager.get_all_classes()
class_options = {c[1]: c[0] for c in classes}

# Check if we came from Manage Exams
selected_exam_id = st.session_state.get('selected_exam_id')

with st.sidebar:
    st.header("Load Existing Exam")
    if not classes:
        st.warning("No classes found. Create one first.")
    else:
        # Default class and exam if coming from redirect
        default_class_idx = 0
        if 'selected_exam_class_id' in st.session_state:
            for i, (name, id) in enumerate(class_options.items()):
                if id == st.session_state['selected_exam_class_id']:
                    default_class_idx = i
                    break
        
        sel_class_name = st.selectbox("Select Class", list(class_options.keys()), index=default_class_idx)
        class_id = class_options[sel_class_name]
        
        exams = db_manager.get_exams_by_class(class_id)
        if exams:
            exam_options = {e[1]: e[0] for e in exams}
            
            default_exam_idx = 0
            if selected_exam_id:
                for i, (name, id) in enumerate(exam_options.items()):
                    if id == selected_exam_id:
                        default_exam_idx = i
                        break
            
            sel_exam_name = st.selectbox("Select Exam", list(exam_options.keys()), index=default_exam_idx)
            
            if st.button("Load Exam Details"):
                exam_details = db_manager.get_exam_details(exam_options[sel_exam_name])
                if exam_details:
                    answer_key = json.loads(exam_details[4])
                    st.session_state['gen_exam_name'] = exam_details[1]
                    st.session_state['gen_num_q'] = len(answer_key)
                    st.session_state['gen_mcq_choices'] = exam_details[5]
                    st.session_state['gen_question_data'] = answer_key # Store types
                    # Clear redirect state once handled
                    if 'selected_exam_id' in st.session_state:
                        del st.session_state['selected_exam_id']
                        del st.session_state['selected_exam_class_id']
                    st.rerun()
        else:
            st.info("No exams found for this class.")

st.divider()

def create_sheet(num_questions=20, exam_name="Exam", mcq_choices=5, question_data=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    width = 210
    height = 297
    margin = 15
    marker_size = 10
    
    # 1. Header (Compact)
    pdf.set_fill_color(0, 0, 0)
    pdf.rect(margin, margin, marker_size, marker_size, 'F') # Top-Left
    pdf.rect(width - margin - marker_size, margin, marker_size, marker_size, 'F') # Top-Right
    
    header_x = margin + 15
    pdf.set_xy(header_x, margin)
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(100, 8, exam_name.upper(), ln=1)
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(header_x, margin + 8)
    pdf.cell(100, 8, f"NAME: {'_'*35}  DATE: {'_'*12}", ln=1)
    
    # 2. Student ID Grid (Y=30)
    id_start_x = 140
    id_start_y = 30
    pdf.set_font("Helvetica", 'B', 9)
    pdf.set_xy(id_start_x, id_start_y - 6)
    pdf.cell(55, 5, "STUDENT ID", ln=1, align='C')
    
    bubble_r = 5.5
    bubble_gap_x = 10
    bubble_gap_y = 8
    
    for col in range(3):
        col_x = id_start_x + (col * bubble_gap_x) + 12
        for row in range(10):
            bx = col_x
            by = id_start_y + (row * bubble_gap_y)
            pdf.ellipse(bx, by, bubble_r, bubble_r)
            pdf.set_font("Helvetica", size=8)
            pdf.set_xy(bx, by)
            pdf.cell(bubble_r, bubble_r, str(row), align='C')
            
    # 3. Answers Grid (Y=115) - Tighter thresholds for compactness
    start_y = 115
    if num_questions <= 12:
        num_cols = 1
        col_width = 80
    elif num_questions <= 24:
        num_cols = 2
        col_width = 75
    else:
        num_cols = 3
        col_width = 60
    
    questions_per_col = (num_questions + num_cols - 1) // num_cols
    bubble_size = 6.5
    bubble_spacing = 9
    row_height = 10 # Reduced from 11 for better density
    
    max_y_reached = start_y
    for q in range(1, num_questions + 1):
        col_idx = (q - 1) // questions_per_col
        q_idx = (q - 1) % questions_per_col
        
        grid_width = num_cols * col_width
        x_base = (width - grid_width) / 2 + (col_idx * col_width)
        y = start_y + (q_idx * row_height)
        max_y_reached = max(max_y_reached, y + row_height)
        
        pdf.set_font("Helvetica", 'B', 11)
        pdf.set_xy(x_base, y)
        pdf.cell(12, row_height, f"{q}.", align='R')
        
        # Check Type (Default to MCQ)
        q_data = question_data.get(str(q), {}) if question_data else {}
        q_type = q_data.get("type", "MCQ") if isinstance(q_data, dict) else "MCQ"
        
        if q_type == "Numeric":
            # Draw a box for writing the number
            box_w = 40
            box_h = row_height - 3
            pdf.rect(x_base + 15, y + 1.5, box_w, box_h)
            pdf.set_font("Helvetica", 'I', 7)
            pdf.set_xy(x_base + 15 + box_w + 2, y)
            # pdf.cell(10, row_height, "(Write Number)")
        else:
            # Draw Bubbles (MCQ)
            options = ['A', 'B', 'C', 'D', 'E'][:mcq_choices]
            pdf.set_font("Helvetica", size=8)
            for i, opt in enumerate(options):
                bx = x_base + 15 + (i * bubble_spacing)
                by = y + (row_height - bubble_size) / 2
                pdf.ellipse(bx, by, bubble_size, bubble_size)
                pdf.set_xy(bx, by)
                pdf.cell(bubble_size, bubble_size, opt, align='C')

    # 4. Bottom Markers (At the end of the active area)
    # This creates a smaller box for the camera to focus on
    bottom_y = max_y_reached + 10
    pdf.set_fill_color(0, 0, 0)
    pdf.rect(margin, bottom_y, marker_size, marker_size, 'F') # Bottom-Left
    pdf.rect(width - margin - marker_size, bottom_y, marker_size, marker_size, 'F') # Bottom-Right
    
    pdf.set_xy(margin, bottom_y + 12)
    pdf.set_font("Helvetica", 'I', 8)
    pdf.cell(width - 2*margin, 5, "Scan standard: Focus the 4 squares in your camera view.", align='C')
            
    return pdf

def create_booklet(question_data, exam_name="Exam"):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, exam_name, ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", size=11)
    
    # Sort questions by number
    sorted_q_nums = sorted([int(k) for k in question_data.keys()])
    
    for q_num in sorted_q_nums:
        q = question_data[str(q_num)]
        if not isinstance(q, dict) or "text" not in q:
            continue
            
        pdf.set_font("Helvetica", 'B', 11)
        pdf.multi_cell(0, 7, f"Question {q_num}: {q['text']}")
        pdf.ln(2)
        
        pdf.set_font("Helvetica", size=10)
        if q["type"] == "MCQ" and "options" in q:
            for i, opt in enumerate(q["options"]):
                letter = chr(65 + i)
                pdf.multi_cell(0, 6, f"  {letter}) {opt}")
        elif q["type"] == "Numeric":
            pdf.multi_cell(0, 6, "  (Write your numerical answer in the box on the answer sheet)")
            
        pdf.ln(5)
        
    return pdf

# Use session state for inputs if available
default_name = st.session_state.get('gen_exam_name', "Midterm Exam")
default_num_q = st.session_state.get('gen_num_q', 20)
default_choices = st.session_state.get('gen_mcq_choices', 5)

exam_title = st.text_input("Exam Name for Header", value=default_name)
num_q = st.number_input("Number of Questions", 1, 100, value=default_num_q)
mcq_choices = st.number_input("MCQ Choices (2-5)", 2, 5, value=default_choices)

if st.button("Generate Answer Sheet"):
    q_data = st.session_state.get('gen_question_data')
    pdf = create_sheet(num_q, exam_title, mcq_choices, question_data=q_data)
    
    # Save to buffer
    pdf_output = pdf.output(dest='S').encode('latin-1')
    b64 = base64.b64encode(pdf_output).decode()
    href = f'<a href="data:application/pdf;base64,{b64}" download="answer_sheet.pdf">Download Answer Sheet (OMR)</a>'
    st.markdown(href, unsafe_allow_html=True)
    st.success("Answer Sheet Generated!")

if st.button("Generate Question Booklet"):
    q_data = st.session_state.get('gen_question_data')
    if q_data and isinstance(next(iter(q_data.values())), dict) and "text" in next(iter(q_data.values())):
        pdf = create_booklet(q_data, exam_title)
        pdf_output = pdf.output(dest='S').encode('latin-1')
        b64 = base64.b64encode(pdf_output).decode()
        href = f'<a href="data:application/pdf;base64,{b64}" download="question_booklet.pdf">Download Question Booklet</a>'
        st.markdown(href, unsafe_allow_html=True)
        st.success("Question Booklet Generated!")
    else:
        st.error("This exam does not have question text stored (likely created manually). Booklet generation is only supported for GIFT imports.")
