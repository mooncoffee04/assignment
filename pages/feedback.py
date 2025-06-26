import streamlit as st
import json
import pandas as pd

# Load feedback.jsonl
feedback_file = "feedback_store.jsonl"

data = []
with open(feedback_file, "r", encoding="utf-8") as f:
    for line in f:
        data.append(json.loads(line))

if not data:
    st.warning("No feedback data found.")
else:
    df = pd.DataFrame(data)

    st.title("Feedback Responses Visualization")

    # Bar chart: Count of good vs bad feedback
    if "is_good" in df.columns:
        feedback_counts = df["is_good"].value_counts()
        st.subheader("Good vs Bad Feedback Count")
        st.bar_chart(feedback_counts)

    # Show raw data
    if st.checkbox("Show raw data"):
        st.write(df)
