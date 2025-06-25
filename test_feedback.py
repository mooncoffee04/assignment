import streamlit as st
import json
from datetime import datetime

FEEDBACK_FILE = "feedback_test.json"

def store_feedback(case_id, doctor_id, is_good):
    entry = {
        "case_id": case_id,
        "doctor_id": doctor_id,
        "rating": "good" if is_good else "poor",
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception as e:
        st.error(f"Error saving feedback: {e}")
        return False

# ---- Session setup ----
if "feedback_given" not in st.session_state:
    st.session_state["feedback_given"] = set()

case_id = "C123"
doctor_id = "D001"
feedback_key = f"{case_id}_{doctor_id}"

st.title("💬 Feedback Test")

if feedback_key in st.session_state["feedback_given"]:
    st.success("✅ Feedback already submitted.")
else:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👍 Good", key="good_btn"):
            if store_feedback(case_id, doctor_id, True):
                st.session_state["feedback_given"].add(feedback_key)
                st.success("Thanks! Good feedback saved.")
                st.rerun()
    with col2:
        if st.button("👎 Poor", key="poor_btn"):
            if store_feedback(case_id, doctor_id, False):
                st.session_state["feedback_given"].add(feedback_key)
                st.warning("Noted! Poor feedback saved.")
                st.rerun()
