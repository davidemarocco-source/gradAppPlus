import streamlit as st
import db_manager
import pandas as pd
import io

st.set_page_config(page_title="Manage Classes", page_icon="🏫")

st.title("🏫 Manage Classes & Students")

tab1, tab2, tab3 = st.tabs(["Create Class", "Add Students (Manual)", "Import Students (CSV)"])

# ----------------- CREATE CLASS -----------------
with tab1:
    st.header("Create New Class")
    new_class_name = st.text_input("Class Name")
    if st.button("Create Class"):
        if new_class_name:
            if db_manager.add_class(new_class_name):
                st.success(f"Class '{new_class_name}' created!")
            else:
                st.error("Class already exists.")
        else:
            st.warning("Please enter a class name.")
            
    st.divider()
    st.subheader("Existing Classes")
    classes = db_manager.get_all_classes()
    if classes:
        for cls_id, cls_name in classes:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{cls_name}**")
            with col2:
                if st.button("🗑️ Delete", key=f"del_cls_{cls_id}"):
                    st.session_state[f"confirm_delete_cls_{cls_id}"] = True
            
            if st.session_state.get(f"confirm_delete_cls_{cls_id}"):
                st.warning(f"Are you sure you want to delete '{cls_name}'? This will delete all its students, exams, and results!")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, Delete Everything", key=f"force_del_cls_{cls_id}"):
                        db_manager.delete_class(cls_id)
                        del st.session_state[f"confirm_delete_cls_{cls_id}"]
                        st.success(f"Class '{cls_name}' deleted.")
                        st.rerun()
                with c2:
                    if st.button("Cancel", key=f"cancel_del_cls_{cls_id}"):
                        del st.session_state[f"confirm_delete_cls_{cls_id}"]
                        st.rerun()
            st.divider()
    else:
        st.info("No classes found.")

# ----------------- MANUAL ADD -----------------
with tab2:
    st.header("Add Single Student")
    
    classes = db_manager.get_all_classes()
    if not classes:
        st.warning("Please create a class first.")
    else:
        class_options = {c[1]: c[0] for c in classes}
        selected_class_name = st.selectbox("Select Class", list(class_options.keys()), key="man_sel")
        selected_class_id = class_options[selected_class_name]
        
        with st.form("add_student_form"):
            col1, col2 = st.columns(2)
            with col1:
                student_name = st.text_input("Student Name")
            with col2:
                educational_id = st.text_input("Student ID (e.g. M2100...)")
                
            submitted = st.form_submit_button("Add Student")
            if submitted:
                if student_name and educational_id:
                    omr_id = db_manager.add_student(student_name, educational_id, selected_class_id)
                    if omr_id:
                        st.success(f"Added {student_name}. OMR ID assigned: **{omr_id}**")
                    else:
                        st.error("Error adding student. ID might be duplicate.")
                else:
                    st.warning("Please fill all fields.")
        
        # Show table
        st.divider()
        col_title, col_clear = st.columns([3, 1])
        with col_title:
            st.subheader(f"Students in {selected_class_name}")
        with col_clear:
            if st.button("🔥 Clear Class", help="Delete all students and results for this class"):
                st.session_state[f"confirm_clear_class_{selected_class_id}"] = True
        
        if st.session_state.get(f"confirm_clear_class_{selected_class_id}"):
            st.warning("Really delete ALL students? This cannot be undone.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, Clear Everything", key=f"force_clear_{selected_class_id}"):
                    db_manager.clear_class_students(selected_class_id)
                    del st.session_state[f"confirm_clear_class_{selected_class_id}"]
                    st.success("Class cleared.")
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"cancel_clear_{selected_class_id}"):
                    del st.session_state[f"confirm_clear_class_{selected_class_id}"]
                    st.rerun()

        students = db_manager.get_students_by_class(selected_class_id)
        if students:
            # Drop the first element (DB id) and use OMR ID + Name + Edu ID
            # But let's keep it for processing and just hide it from the user
            df_students = pd.DataFrame(students, columns=["DB_ID", "Name", "Edu ID", "OMR ID"])
            
            # Create a user-friendly sequential index starting from 0
            df_students.insert(0, "No.", range(len(df_students)))
            
            # Display only the columns the user cares about
            st.dataframe(df_students[["No.", "Name", "Edu ID", "OMR ID"]], hide_index=True)
        else:
            st.info("No students in this class.")

# ----------------- CSV IMPORT -----------------
with tab3:
    st.header("Bulk Import from CSV")
    
    classes = db_manager.get_all_classes()
    if not classes:
        st.warning("Please create a class first.")
    else:
        class_options_csv = {c[1]: c[0] for c in classes}
        selected_class_name_csv = st.selectbox("Select Target Class", list(class_options_csv.keys()), key="csv_sel")
        selected_class_id_csv = class_options_csv[selected_class_name_csv]
        
        st.info("CSV headers: `Name`, `ID` (Educational ID). Optional: `OMR_ID` (to force bubble numbering).")
        
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.write("Preview:")
                st.dataframe(df.head())
                
                col_map = {c.lower().replace(" ", ""): c for c in df.columns}
                
                id_col = col_map.get("id")
                cognome_col = col_map.get("cognome")
                nome_col = col_map.get("nome")
                name_col = col_map.get("name")
                omr_id_col = col_map.get("omrid") # New: support OMR_ID
                
                valid = False
                if id_col:
                    if cognome_col and nome_col:
                        valid = True
                    elif name_col:
                        valid = True
                
                if not valid:
                    st.error("CSV must contain columns: 'ID', 'COGNOME', 'NOME' (or 'ID', 'Name')")
                else:
                    if st.button("Import Students"):
                        count = 0
                        errors = 0
                        progress = st.progress(0)
                        
                        total = len(df)
                        for i, row in df.iterrows():
                            eid = str(row[id_col])
                            
                            oid = None
                            if omr_id_col:
                                try:
                                    oid = int(row[omr_id_col])
                                except:
                                    oid = None
                            
                            if cognome_col and nome_col:
                                c = str(row[cognome_col])
                                n = str(row[nome_col])
                                nm = f"{c} {n}"
                            else:
                                nm = str(row[name_col])
                            
                            res = db_manager.add_student(nm, eid, selected_class_id_csv, omr_id=oid)
                            if res:
                                count += 1
                            else:
                                errors += 1
                            progress.progress((i + 1) / total)
                            
                        st.success(f"Imported {count} students. {errors} duplicates/errors.")
                        # Show updated list
                        students = db_manager.get_students_by_class(selected_class_id_csv)
                        if students:
                            df_students = pd.DataFrame(students, columns=["ID", "Name", "Edu ID", "OMR ID"])
                            st.dataframe(df_students, hide_index=True)
                            
            except Exception as e:
                st.error(f"Error parsing CSV: {e}")
