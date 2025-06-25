import streamlit as st
import pandas as pd

def render_case_dashboard(df, doctor_id):
    st.markdown("## 📋 Your Assigned Cases")

    # --- Search and Filters ---
    st.markdown("### 🔍 Filter Cases")
    search_text = st.text_input("Search by Patient ID or Name", "")
    filtered_df = df.copy()

    if search_text:
        filtered_df = filtered_df[
            filtered_df["PatientID"].str.contains(search_text, case=False) |
            filtered_df["PatientName"].str.contains(search_text, case=False)
        ]

    st.markdown(f"### 🧾 {len(filtered_df)} Case(s) Found")

    # --- Table Summary View ---
    table_df = filtered_df[["CaseID", "PatientID", "PatientName"]].copy()
    table_df["Summary?"] = filtered_df["Summary"].apply(lambda x: "✅" if x.strip() else "⚠️ Missing")
    table_df["Lab Report?"] = filtered_df["LabReport"].apply(lambda x: "✅" if x.strip() else "❌")
    table_df["Scan Report?"] = filtered_df["ScanReport"].apply(lambda x: "✅" if x.strip() else "❌")

    st.dataframe(table_df, use_container_width=True)

    # --- Individual Case Cards ---
    st.markdown("### 📂 Explore Case Details")
    for _, row in filtered_df.iterrows():
        with st.expander(f"Case {row['CaseID']} – {row['PatientName']} ({row['PatientID']})"):
            st.markdown(f"**Case Summary:**\n\n{row['Summary'] or '⚠️ No summary saved yet.'}")

            col1, col2 = st.columns(2)
            if row["LabReport"]:
                col1.markdown(f"🧪 [Lab Report]({row['LabReport']})")
            else:
                col1.warning("No lab report")

            if row["ScanReport"]:
                col2.markdown(f"🩻 [Radiology Scan]({row['ScanReport']})")
            else:
                col2.warning("No scan uploaded")

            # Trigger detailed view (optional)
            if st.button("🔍 Open Full Case View", key=f"open_{row['CaseID']}"):
                st.session_state["selected_case_id"] = row["CaseID"]
                st.rerun()
