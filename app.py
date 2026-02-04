import streamlit as st
import db_manager

st.set_page_config(
    page_title="OpenOMR - Open Source Grading",
    page_icon="📝",
    layout="wide"
)

st.title("📝 OpenOMR Grading System")

st.markdown("""
Welcome to **OpenOMR**, a ZipGrade-like grading application built with Python.

### Features
- **Manage Classes**: create classes and add students.
- **Manage Exams**: create answer keys for your tests.
- **Scanner**: Use your webcam or upload images to grade automatically.
- **Results**: Export grades.
- **Sheet Generator**: Create printable answer sheets.

### Getting Started
1. Go to **Manage Classes** to create a class.
2. Go to **Manage Exams** to set up a new test key.
3. Print sheets using **Sheet Generator**.
4. Grade them using **Scanner**.
""")

# Initialize DB if needed (though db_manager does this on import check, calling helper ensures it)
if "db_init" not in st.session_state:
    db_manager.init_db()
    st.session_state["db_init"] = True
