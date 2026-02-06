import streamlit as st
import db_manager
import pandas as pd

st.set_page_config(page_title="Results", page_icon="📊")
st.title("📊 Exam Results")

# Select Exam
classes = db_manager.get_all_classes()
if not classes:
    st.warning("No data.")
    st.stop()
class_map = {c[1]: c[0] for c in classes}
selected_class = st.selectbox("Class", list(class_map.keys()))

exams = db_manager.get_exams_by_class(class_map[selected_class])
if not exams:
    st.info("No exams for this class.")
    st.stop()

exam_map = {e[1]: e[0] for e in exams} # Name -> ID. Note: duplicate names possible, ideally use ID in label
exam_opts = {f"{e[1]} ({e[2]})": e[0] for e in exams}
selected_exam_label = st.selectbox("Exam", list(exam_opts.keys()))
selected_exam_id = exam_opts[selected_exam_label]

is_master = "(Master)" in selected_exam_label

if is_master:
    results = db_manager.get_results_by_master_exam(selected_exam_id)
else:
    results = db_manager.get_results_by_exam(selected_exam_id)
    
# results: id, student_id, name, educational_id, omr_id, score, exam_name

if results:
    df = pd.DataFrame(results, columns=["Result ID", "Student ID", "Name", "Edu ID", "OMR ID", "Total", "MCQ", "Num", "Exam/Version"])
    
    # Calculate stats
    avg = df["Total"].mean()
    st.metric("Average Score", f"{avg:.2f}")
    
    # Custom table with delete buttons
    st.write("---")
    header_cols = st.columns([1, 2, 2, 1, 1, 1, 1, 2, 1])
    header_labels = ["ID", "Name", "Edu ID", "OID", "Tot", "MCQ", "Num", "Exam/Version", "Act"]
    for col, label in zip(header_cols, header_labels):
        col.write(f"**{label}**")
        
    for i, row in df.iterrows():
        res_id = row["Result ID"]
        cols = st.columns([1, 2, 2, 1, 1, 1, 1, 2, 1])
        cols[0].write(f"{res_id}")
        cols[1].write(f"{row['Name']}")
        cols[2].write(f"{row['Edu ID']}")
        cols[3].write(f"{row['OMR ID']}")
        cols[4].write(f"{row['Total']}")
        cols[5].write(f"{row['MCQ']}")
        cols[6].write(f"{row['Num']}")
        cols[7].write(f"{row['Exam/Version']}")
        
        if cols[8].button("🗑️", key=f"del_res_{res_id}"):
            db_manager.delete_result(res_id)
            st.success(f"Result {res_id} deleted.")
            st.rerun()
            
    st.divider()
    csv = df.drop(columns=["Result ID"]).to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name='grades.csv',
        mime='text/csv',
    )
else:
    st.info("No results graded yet.")
