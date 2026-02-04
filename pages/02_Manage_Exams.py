import streamlit as st
import db_manager
import datetime
import json
import gift_parser
import io

st.set_page_config(page_title="Manage Exams", page_icon="📝")

st.title("📝 Header Exams & Keys")

classes = db_manager.get_all_classes()
if not classes:
    st.warning("Please create a class first.")
    st.stop()
    
class_options = {c[1]: c[0] for c in classes}

with st.expander("Create New Exam", expanded=True):
    with st.form("create_exam_form"):
        exam_name = st.text_input("Exam Name")
        selected_class = st.selectbox("Class", list(class_options.keys()))
        exam_date = st.date_input("Date", datetime.date.today())
        
        st.subheader("Answer Key")
        col_key1, col_key2 = st.columns(2)
        with col_key1:
            num_questions = st.number_input("Number of Questions", min_value=1, max_value=100, value=10)
        with col_key2:
            mcq_choices = st.number_input("MCQ Choices (2-5)", min_value=2, max_value=5, value=5)
        
        submitted = st.form_submit_button("Start Key Definition")
        
        if submitted:
            if exam_name:
                st.session_state['draft_exam'] = {
                    "name": exam_name,
                    "class_id": class_options[selected_class],
                    "date": str(exam_date),
                    "num_questions": num_questions,
                    "mcq_choices": mcq_choices
                }
                st.rerun()
            else:
                st.error("Exam name required")

with st.expander("Import GIFT File", expanded=False):
    st.info("Upload a .gift file to automatically create an exam with shuffled questions and answers.")
    gift_name = st.text_input("GIFT Exam Name", placeholder="e.g. Psychology Final")
    gift_class = st.selectbox("Class for GIFT", list(class_options.keys()), key="gift_class")
    gift_date = st.date_input("Date for GIFT", datetime.date.today(), key="gift_date")
    gift_file = st.file_uploader("Upload .gift file", type=["gift", "txt"])
    
    if st.button("Process & Shuffle GIFT"):
        if not gift_name:
            st.error("Exam name required")
        elif gift_file is not None:
            content = gift_file.getvalue().decode("utf-8")
            raw_questions = gift_parser.parse_gift(content)
            if not raw_questions:
                st.error("No questions found in file. Please check GIFT format.")
            else:
                shuffled_exam = gift_parser.shuffle_exam(raw_questions)
                # Convert to the format expected by db_manager (1-based keys for OMR)
                # And also store the rich data for booklet generation
                final_key = {}
                for i, q in enumerate(shuffled_exam):
                    # We store the whole question object in the answer key 
                    # so we can reconstruct the booklet later
                    final_key[i+1] = q
                
                db_manager.create_exam(gift_name, class_options[gift_class], gift_date, final_key)
                st.success(f"Exam '{gift_name}' created with {len(shuffled_exam)} shuffled questions!")
                st.rerun()
        else:
            st.error("Please upload a file")

if 'draft_exam' in st.session_state:
    st.divider()
    draft = st.session_state['draft_exam']
    st.subheader(f"Define Key for: {draft['name']}")
    
    with st.form("key_form"):
        key_data = {}
        cols = st.columns(5)
        mcq_options = ["A", "B", "C", "D", "E"][:draft['mcq_choices']]
        
        for q in range(1, draft['num_questions'] + 1):
            with cols[(q-1)%5]:
                q_type = st.selectbox(f"Q{q} Type", ["MCQ", "Numeric"], key=f"q_type_{q}", label_visibility="collapsed")
                
                if q_type == "MCQ":
                   ans = st.selectbox(f"Q{q} Ans", mcq_options, key=f"q_{q}")
                   key_data[q] = {"ans": ans, "type": "MCQ"}
                else:
                   ans = st.number_input(f"Q{q} Val", key=f"q_{q}", step=0.1)
                   key_data[q] = {"ans": ans, "type": "Numeric"}

        if st.form_submit_button("Save Exam"):
            db_manager.create_exam(draft['name'], draft['class_id'], draft['date'], key_data, draft['mcq_choices'])
            st.success("Exam Saved!")
            del st.session_state['draft_exam']
            st.rerun()

st.divider()
st.subheader("Existing Exams")
# List exams by class
selected_view_class = st.selectbox("Filter by Class", ["All"] + list(class_options.keys()))

if selected_view_class == "All":
    # Need a get_all_exams function or loop through classes. 
    # For simplicity, let's just show raw list if we had a generic function, 
    # but db helper is by_class. I'll just iterate if "All" or fix db helper.
    # Let's just prompt user to select class.
    st.info("Select a class to view exams")
else:
    exams = db_manager.get_exams_by_class(class_options[selected_view_class])
    if exams:
        for ex in exams:
            with st.expander(f"{ex[1]} ({ex[2]})"):
                details = db_manager.get_exam_details(ex[0])
                st.json(json.loads(details[4]))
                
                # --- Actions ---
                col_ex1, col_ex2 = st.columns(2)
                with col_ex1:
                    if st.button("🖨️ Generate Sheet", key=f"gen_{ex[0]}"):
                        st.session_state['selected_exam_id'] = ex[0]
                        st.session_state['selected_exam_class_id'] = class_options[selected_view_class]
                        answer_key = json.loads(details[4])
                        st.session_state['gen_exam_name'] = ex[1]
                        st.session_state['gen_num_q'] = len(answer_key)
                        st.switch_page("pages/05_Sheet_Generator.py")
                
                with col_ex2:
                    if st.button("🗑️ Delete Exam", key=f"del_ex_{ex[0]}"):
                        st.session_state[f"confirm_delete_ex_{ex[0]}"] = True
                
                if st.session_state.get(f"confirm_delete_ex_{ex[0]}"):
                    st.warning(f"Are you sure you want to delete '{ex[1]}'? This will delete all its results!")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, Delete Exam", key=f"force_del_ex_{ex[0]}"):
                            db_manager.delete_exam(ex[0])
                            del st.session_state[f"confirm_delete_ex_{ex[0]}"]
                            st.success(f"Exam '{ex[1]}' deleted.")
                            st.rerun()
                    with c2:
                        if st.button("Cancel", key=f"cancel_del_ex_{ex[0]}"):
                            del st.session_state[f"confirm_delete_ex_{ex[0]}"]
                            st.rerun()
