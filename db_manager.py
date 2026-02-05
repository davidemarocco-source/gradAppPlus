import streamlit as st
from sqlalchemy import text
import json

def get_connection():
    # This uses the configuration in .streamlit/secrets.toml
    return st.connection("sql", type="sql")

def init_db():
    conn = get_connection()
    with conn.session as s:
        # Classes Table
        s.execute(text('''CREATE TABLE IF NOT EXISTS classes (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE
                    )'''))
        
        # Students Table
        s.execute(text('''CREATE TABLE IF NOT EXISTS students (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        educational_id TEXT, 
                        omr_id INTEGER,
                        class_id INTEGER REFERENCES classes(id),
                        UNIQUE(class_id, omr_id),
                        UNIQUE(class_id, educational_id)
                    )'''))
        
        # Exams Table
        s.execute(text('''CREATE TABLE IF NOT EXISTS exams (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        class_id INTEGER REFERENCES classes(id),
                        date TEXT,
                        answer_key TEXT,
                        mcq_choices INTEGER DEFAULT 5,
                        parent_id INTEGER REFERENCES exams(id)
                    )'''))
        
        # Results Table
        s.execute(text('''CREATE TABLE IF NOT EXISTS results (
                        id SERIAL PRIMARY KEY,
                        exam_id INTEGER REFERENCES exams(id),
                        student_id INTEGER REFERENCES students(id),
                        score DOUBLE PRECISION,
                        answers TEXT,
                        image_path TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )'''))
        
        # Migration: Add mcq_choices if it doesn't exist
        try:
            s.execute(text("ALTER TABLE exams ADD COLUMN IF NOT EXISTS mcq_choices INTEGER DEFAULT 5"))
            s.execute(text("ALTER TABLE exams ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES exams(id)"))
        except Exception:
            # Column might already exist or DB might not support IF NOT EXISTS in ALTER (though Postgres does)
            pass
            
        s.commit()

# --- Classes ---
def add_class(name):
    conn = get_connection()
    try:
        with conn.session as s:
            s.execute(text("INSERT INTO classes (name) VALUES (:name)"), {"name": name})
            s.commit()
        return True
    except Exception:
        return False

def get_all_classes():
    conn = get_connection()
    res = conn.query("SELECT id, name FROM classes", ttl=0)
    return res.values.tolist()

def get_class_name(class_id):
    conn = get_connection()
    res = conn.query("SELECT name FROM classes WHERE id=:id", params={"id": class_id}, ttl=0)
    return res["name"].iloc[0] if not res.empty else None

# --- Students ---
def add_student(name, educational_id, class_id, omr_id=None):
    conn = get_connection()
    try:
        with conn.session as s:
            if omr_id is None:
                # Find next omr_id
                res = s.execute(text("SELECT MAX(omr_id) FROM students WHERE class_id=:class_id"), 
                                {"class_id": class_id}).fetchone()
                max_id = res[0]
                next_omr_id = 0 if max_id is None else max_id + 1
            else:
                next_omr_id = omr_id
            
            s.execute(text("INSERT INTO students (name, educational_id, omr_id, class_id) VALUES (:name, :eid, :oid, :cid)"), 
                      {"name": name, "eid": educational_id, "oid": next_omr_id, "cid": class_id})
            s.commit()
            return next_omr_id
    except Exception:
        return None

def clear_class_students(class_id):
    conn = get_connection()
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM results WHERE student_id IN (SELECT id FROM students WHERE class_id=:id)"), {"id": class_id})
            s.execute(text("DELETE FROM students WHERE class_id=:id"), {"id": class_id})
            s.commit()
        return True
    except Exception:
        return False

def get_students_by_class(class_id):
    conn = get_connection()
    res = conn.query("SELECT id, name, educational_id, omr_id FROM students WHERE class_id=:id", 
                    params={"id": class_id}, ttl=0)
    return res.values.tolist()

def get_student_by_omr(class_id, omr_id):
    conn = get_connection()
    res = conn.query("SELECT id, name, educational_id, omr_id FROM students WHERE class_id=:cid AND omr_id=:oid", 
                    params={"cid": class_id, "oid": omr_id}, ttl=0)
    return res.iloc[0].tolist() if not res.empty else None

# --- Exams ---
def create_exam(name, class_id, date, answer_key, mcq_choices=5, parent_id=None):
    conn = get_connection()
    key_json = json.dumps(answer_key)
    with conn.session as s:
        res = s.execute(text("INSERT INTO exams (name, class_id, date, answer_key, mcq_choices, parent_id) VALUES (:name, :cid, :date, :key, :choices, :pid) RETURNING id"),
                  {"name": name, "cid": class_id, "date": str(date), "key": key_json, "choices": mcq_choices, "pid": parent_id})
        exam_id = res.fetchone()[0]
        s.commit()
    return exam_id

def get_exams_by_class(class_id):
    conn = get_connection()
    res = conn.query("SELECT id, name, date, parent_id FROM exams WHERE class_id=:id", params={"id": class_id}, ttl=0)
    return res.values.tolist()

def get_exam_details(exam_id):
    conn = get_connection()
    res = conn.query("SELECT id, name, class_id, date, answer_key, mcq_choices, parent_id FROM exams WHERE id=:id", params={"id": exam_id}, ttl=0)
    return res.iloc[0].tolist() if not res.empty else None

def get_exam_versions(parent_id):
    conn = get_connection()
    res = conn.query("SELECT id, name, date, answer_key, mcq_choices FROM exams WHERE parent_id=:pid ORDER BY name ASC", params={"pid": parent_id}, ttl=0)
    return res.values.tolist()

# --- Results ---
def save_result(exam_id, student_id, score, answers, image_path):
    conn = get_connection()
    answers_json = json.dumps(answers)
    with conn.session as s:
        s.execute(text("INSERT INTO results (exam_id, student_id, score, answers, image_path) VALUES (:eid, :sid, :score, :ans, :path)"),
                  {"eid": exam_id, "sid": student_id, "score": score, "ans": answers_json, "path": image_path})
        s.commit()

def get_results_by_exam(exam_id):
    conn = get_connection()
    sql = '''SELECT r.id, r.student_id, s.name, s.educational_id, s.omr_id, r.score 
             FROM results r 
             JOIN students s ON r.student_id = s.id 
             WHERE r.exam_id=:id'''
    res = conn.query(sql, params={"id": exam_id}, ttl=0)
    return res.values.tolist()

# --- Deletions ---
def delete_class(class_id):
    conn = get_connection()
    with conn.session as s:
        # Cascade manually for safety or rely on constraints if set to CASCADE
        s.execute(text("DELETE FROM results WHERE student_id IN (SELECT id FROM students WHERE class_id=:id)"), {"id": class_id})
        s.execute(text("DELETE FROM results WHERE exam_id IN (SELECT id FROM exams WHERE class_id=:id)"), {"id": class_id})
        s.execute(text("DELETE FROM students WHERE class_id=:id"), {"id": class_id})
        # Delete version exams first to satisfy foreign key constraints
        s.execute(text("DELETE FROM exams WHERE class_id=:id AND parent_id IS NOT NULL"), {"id": class_id})
        s.execute(text("DELETE FROM exams WHERE class_id=:id"), {"id": class_id})
        s.execute(text("DELETE FROM classes WHERE id=:id"), {"id": class_id})
        s.commit()

def delete_exam(exam_id):
    conn = get_connection()
    with conn.session as s:
        # 1. Delete results for all versions of this exam (if it's a master)
        s.execute(text("DELETE FROM results WHERE exam_id IN (SELECT id FROM exams WHERE parent_id=:id)"), {"id": exam_id})
        
        # 2. Delete the versions themselves
        s.execute(text("DELETE FROM exams WHERE parent_id=:id"), {"id": exam_id})
        
        # 3. Delete results for this specific exam
        s.execute(text("DELETE FROM results WHERE exam_id=:id"), {"id": exam_id})
        
        # 4. Finally delete the exam itself
        s.execute(text("DELETE FROM exams WHERE id=:id"), {"id": exam_id})
        s.commit()

def delete_result(result_id):
    conn = get_connection()
    with conn.session as s:
        s.execute(text("DELETE FROM results WHERE id=:id"), {"id": result_id})
        s.commit()

# Initialize tables
if __name__ == "__main__":
    init_db()
