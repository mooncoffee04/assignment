import streamlit as st
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import pandas as pd
from audiorecorder import audiorecorder
from agents.prompt_builder import build_multimodal_prompt
from agents.file_parser import parse_lab_file, encode_image
from agents.gemini_agent import call_gemini
from agents.gemini_agent import store_feedback_to_file
from datetime import datetime, date # Import datetime and date for filtering
from dateutil import parser
import pytz # Ensure pytz is imported at the top level
import requests # Added for SeaweedFS deletion
import re
import torch


# --------- Date-Time Parser --------------------
def format_datetime(datetime_value):
    """
    Centralized datetime formatting function
    Handles various datetime formats and returns a consistent display format
    """
    if not datetime_value:
        return "Unknown"
    try:
        # Handle different datetime formats
        if isinstance(datetime_value, str):
            dt = parser.isoparse(datetime_value)
        else:
            dt = datetime_value
        # If datetime is timezone-naive, assume it's UTC (common for Neo4j)
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        # Convert to your local timezone (adjust as needed)
        local_tz = pytz.timezone('Asia/Kolkata')  # Since you're in Mumbai
        dt_local = dt.astimezone(local_tz)
        return dt_local.strftime("%d %b %Y, %I:%M %p")
    except Exception as e:
        return str(datetime_value)

# -------- Load env and connect to Neo4j --------
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# -------- UI Config --------
st.set_page_config(page_title="Clinical Assistant", page_icon="🩺", layout="wide")
st.markdown("""
<style>
/* Target Streamlit text input and text area elements */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background-color: black !important;
    color: white !important; /* Text color inside the box */
    border: 1px solid #333 !important; /* Optional: add a subtle border */
    border-radius: 5px !important; /* Optional: rounded corners */
}
/* Label text color for text inputs and text areas */
.stTextInput > label,
.stTextArea > div > div > label {
    color: #FAFAFA !important; /* Lighter color for labels */
}
/* Adjust general text color if needed (e.g., if you only apply this CSS) */
body {
    color: #FAFAFA; /* Default text color for the app content */
}
/* Ensure placeholder text is visible on black background */
.stTextInput > div > div > input::placeholder,
.stTextArea > div > div > textarea::placeholder {
    color: #BBBBBB !important; /* Lighter color for placeholder */
}
</style>
""", unsafe_allow_html=True)

# -------- Utility Functions (keep these here for app.py's own use) --------
# The add_new_case_to_neo4j and delete_case_from_neo4j will be moved to the new page.
def fetch_all_doctors():
    with driver.session() as session:
        result = session.run("MATCH (d:Doctor) RETURN d.id AS id, d.name AS name, d.role AS role")
        return [{"id": r["id"], "name": r["name"], "role": r["role"]} for r in result]

def get_doctor_name(doctor_id):
    with driver.session() as session:
        result = session.run("MATCH (d:Doctor {id: $doctor_id}) RETURN d.name AS name", {"doctor_id": doctor_id})
        r = result.single()
        return r["name"] if r else "Doctor"

def register_doctor_login(doctor_id, password):
    with driver.session() as session:
        if not session.run("MATCH (d:Doctor {id: $doctor_id}) RETURN d", {"doctor_id": doctor_id}).single():
            return False, "Doctor ID not found in system."
        if session.run("MATCH (d:DoctorLogin {id: $doctor_id}) RETURN d", {"doctor_id": doctor_id}).single():
            return False, "Doctor already registered."
        session.run("CREATE (d:DoctorLogin {id: $doctor_id, password: $password})", {"doctor_id": doctor_id, "password": password})
        return True, "Registration successful!"

def validate_doctor_login(doctor_id, password):
    with driver.session() as session:
        return session.run(
            "MATCH (d:DoctorLogin {id: $doctor_id, password: $password}) RETURN d",
            {"doctor_id": doctor_id, "password": password}
        ).single() is not None

def fetch_cases_for_doctor(doctor_id):
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Doctor {id: $doctor_id})-[:HANDLES]->(c:Case)-[:BELONGS_TO]->(p:Patient)
            RETURN c.case_id AS CaseID,
                   p.id AS PatientID,
                   p.name AS PatientName,
                   c.case_summary AS Summary,
                   c.created_at AS CreatedAt
            ORDER BY c.created_at DESC
        """, {"doctor_id": doctor_id})
        return [r.data() for r in result]


# -------- Streamlit App UI --------
st.markdown("# 🩺 Multimodal Clinical Insight Assistant")

# Show login/registration if not logged in
if "logged_in_doctor" not in st.session_state:
    doctors = fetch_all_doctors()
    doctor_df = pd.DataFrame(doctors)
    st.markdown("### 👩‍⚕️ Approved Doctors")
    st.dataframe(doctor_df.rename(columns={"id": "Doctor ID", "name": "Name", "Specialization": "Role"}), use_container_width=True)
    tabs = st.tabs(["Login", "Register"])
    with tabs[0]:
        st.subheader("Login")
        login_id = st.text_input("Doctor ID")
        login_password = st.text_input("Password", type="password")
        if st.button("Login"):
            with driver.session() as session:
                registered = session.run("MATCH (d:DoctorLogin {id: $login_id}) RETURN d", {"login_id": login_id}).single()
                if not registered:
                    st.warning("⚠️ Doctor not registered. Please register before logging in.")
                elif validate_doctor_login(login_id, login_password):
                    st.session_state.logged_in_doctor = login_id
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Please try again.")

    with tabs[1]:
        st.subheader("Register")
        reg_id = st.selectbox("Choose Your Doctor ID", [doc["id"] for doc in doctors])
        reg_password = st.text_input("Create Password", type="password")
        if st.button("Register"):
            success, msg = register_doctor_login(reg_id, reg_password)
            if success:
                st.success(msg)
            else:
                st.warning(msg)
                
# Show dashboard if logged in
else:
    doctor_id = st.session_state.logged_in_doctor

    with driver.session() as session:
        result = session.run("MATCH (d:Doctor {id: $doctor_id}) RETURN d.name AS name, d.role AS role", {"doctor_id": doctor_id})
        record = result.single()
        doctor_name = record["name"] if record else "Unknown"
        doctor_role = record["role"] if record else "Unknown"
    st.success(f"👋 Welcome, {doctor_name} ({doctor_role}, {doctor_id})")
    st.markdown("---") # Separator


    # -------- Case Search and Filtering --------

    st.markdown("## 🔍 Case Search & Filtering")
    with st.expander("Apply Filters"):
        col_pid, col_pname = st.columns(2)
        patient_id_filter = col_pid.text_input("Filter by Patient ID", key="filter_patient_id")
        patient_name_filter = col_pname.text_input("Filter by Patient Name", key="filter_patient_name")
        col_date_start, col_date_end = st.columns(2)
        date_start_filter = col_date_start.date_input("Start Date", value=None, key="filter_date_start")
        date_end_filter = col_date_end.date_input("End Date", value=None, key="filter_date_end")
        filter_button_col, clear_button_col = st.columns(2)
        if filter_button_col.button("Apply Filters", key="apply_filters_btn"):
            st.session_state["filter_active"] = True
            st.session_state["patient_id_filter"] = patient_id_filter
            st.session_state["patient_name_filter"] = patient_name_filter
            st.session_state["date_start_filter"] = date_start_filter
            st.session_state["date_end_filter"] = date_end_filter
            st.rerun()
        if clear_button_col.button("Clear Filters", key="clear_filters_btn"):
            st.session_state["filter_active"] = False
            st.session_state["patient_id_filter"] = ""
            st.session_state["patient_name_filter"] = ""
            st.session_state["date_start_filter"] = None
            st.session_state["date_end_filter"] = None
            st.rerun()
    # -------- Assigned Cases (now with filtering) --------
    cases = fetch_cases_for_doctor(doctor_id)
    if cases:
        df_all_cases = pd.DataFrame(cases)
        # Convert 'CreatedAt' to datetime objects for proper comparison
        df_all_cases['CreatedAt_dt'] = df_all_cases['CreatedAt'].apply(lambda x: x if isinstance(x, datetime) else parser.isoparse(x) if isinstance(x, str) else None)
        df_all_cases['CreatedAt'] = df_all_cases['CreatedAt'].apply(format_datetime) # Format for display
        filtered_df = df_all_cases.copy()
        if st.session_state.get("filter_active", False):
            # Apply Patient ID filter
            if st.session_state.get("patient_id_filter"):
                filtered_df = filtered_df[filtered_df['PatientID'].str.contains(st.session_state["patient_id_filter"], case=False, na=False)]
            # Apply Patient Name filter
            if st.session_state.get("patient_name_filter"):
                filtered_df = filtered_df[filtered_df['PatientName'].str.contains(st.session_state["patient_name_filter"], case=False, na=False)]
            # Apply Date Range filter
            if st.session_state.get("date_start_filter"):
                start_dt = datetime.combine(st.session_state["date_start_filter"], datetime.min.time()).astimezone(pytz.UTC)
                filtered_df = filtered_df[filtered_df['CreatedAt_dt'] >= start_dt]
            if st.session_state.get("date_end_filter"):
                end_dt = datetime.combine(st.session_state["date_end_filter"], datetime.max.time()).astimezone(pytz.UTC)
                filtered_df = filtered_df[filtered_df['CreatedAt_dt'] <= end_dt]
        st.markdown("### 📝 Assigned Cases")
        if not filtered_df.empty:
            # Display cases as a dataframe
            st.dataframe(filtered_df[['CaseID', 'PatientID', 'PatientName', 'Summary', 'CreatedAt']], use_container_width=True)
        else:
            st.info("No cases match your current filters.")
        st.markdown("---") # Separator
    
    # --------- GLOBAL Ask via Command ------------
    st.markdown("## 🔎 Ask via Command (Global Retrieval)")
    
    command_mode = st.radio(
        "Choose command input mode",
        ["🧾 Type Command", "🎤 Dictate with Mic"],
        key="cmd_input_mode_global"
    )

    user_command = "" # Initialize user_command

    if command_mode == "🧾 Type Command":
        user_command = st.text_input(
            "Type your query (e.g. 'Show chest X-ray for case 45' or 'List all patients')",
            key="typed_cmd_input_global"
        )
        if user_command and st.button("💬 Run Command", key="run_typed_cmd_global"):
            st.session_state["execute_command"] = user_command
            st.session_state["command_source"] = "typed"
            st.rerun()

    elif command_mode == "🎤 Dictate with Mic":
        import whisper
        import tempfile
        import os

        audio = audiorecorder("🎤 Click to Record", "🛑 Stop Recording", key="cmd_audio_recorder_global")

        if len(audio) > 0:
            st.audio(audio.export().read(), format="audio/wav")

            if st.button("📝 Transcribe & Run Command", key="run_mic_cmd_global"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    audio.export(tmp.name, format="wav")
                    temp_path = tmp.name

                with st.spinner("Transcribing audio..."):
                    model = whisper.load_model("base")
                    result = model.transcribe(temp_path)
                    os.remove(temp_path)
                    transcription = result["text"]
                    st.json(result)
                
                st.success("✅ Transcription complete!")
                st.text_area("Transcribed Command", value=transcription, height=70, disabled=True, key="transcribed_cmd_display_global")
                
                st.session_state["execute_command"] = transcription
                st.session_state["command_source"] = "dictated"
                st.rerun()

    # Process the command if a command was set to be executed
    if "execute_command" in st.session_state and st.session_state["execute_command"]:
        from agents.command_processor import process_natural_language_command
        
        user_command_to_execute = st.session_state["execute_command"]
        st.info(f"Executing command: '{user_command_to_execute}' (Source: {st.session_state['command_source']})")

        with st.spinner("Processing your command..."):
            try:
                # IMPORTANT: The 'case_context' parameter has been removed from this call.
                # You MUST update agents/command_processor.py to handle commands
                # that might contain patient/case IDs within the command string itself,
                # or global queries that do not require a specific case.
                result = process_natural_language_command(
                    command=user_command_to_execute,
                    driver=driver
                )
                
                if result['success']:
                    
                    st.code(result['query'], language='cypher') # Uncomment for debugging Cypher query
                    st.json(result)
                    
                    if result['data']:
                        st.markdown("### 📊 Results")
                        
                        if isinstance(result['data'], list) and len(result['data']) > 0:
                            first_record = result['data'][0]
                            
                            if 'url' in first_record:
                                st.markdown("**Reports:**")
                                for i, record in enumerate(result['data'], 1):
                                    report_type = record.get('type', 'Report')
                                    st.markdown(f"🔗 [Open {report_type.title()} Report #{i}]({record['url']})")
                            
                            elif 'summary' in first_record:
                                st.text_area("Case Summary", value=first_record['summary'], height=200, disabled=True)
                            
                            elif 'name' in first_record or 'patient_name' in first_record:
                                df_results = pd.DataFrame(result['data'])
                                st.dataframe(df_results, use_container_width=True)
                            
                            else:
                                df_results = pd.DataFrame(result['data'])
                                st.dataframe(df_results, use_container_width=True)
                        
                        elif isinstance(result['data'], dict):
                            if 'summary' in result['data']:
                                st.text_area("Case Summary", value=result['data']['summary'], height=200, disabled=True)
                            elif 'url' in result['data']:
                                report_type = result['data'].get('type', 'Report')
                                st.markdown(f"🔗 [Open {report_type.title()} Report]({result['data']['url']})")
                            else:
                                st.json(result['data'])
                        
                        else:
                            st.info("Query executed successfully but returned no data.")
                    
                    else:
                        st.info("Query executed successfully but returned no data.")
                
                else:
                    st.error(f"❌ Error: {result['error']}")
                    if result.get('suggestion'):
                        st.info(f"💡 Suggestion: {result['suggestion']}")
            
            except Exception as e:
                st.error(f"❌ An error occurred while processing your command: {str(e)}")
                st.info("💡 Try rephrasing your command or check if the system is properly configured.")
        
        # Clear the command from session state after execution
        del st.session_state["execute_command"]
        del st.session_state["command_source"]

    st.markdown("---") # Separator

    # -------- Patient-wise Report Viewer --------
    st.markdown("## 📁 All Uploaded Reports & Clinical Insights")
    with driver.session() as session:
        reports = session.run("""
            MATCH (p:Patient)<-[:BELONGS_TO]-(c:Case)-[:HAS_REPORT]->(r:UploadedReport)
            RETURN p.name AS PatientName, p.id AS PatientID, c.case_id AS CaseID,
                r.type AS Type, r.url AS URL, r.uploaded_at AS UploadedAt
            ORDER BY r.uploaded_at DESC
        """).data()
    if reports:
        lab_reports = []
        scan_reports = []
        clinical_insights = []  # New category for prescriptions/insights
        for r in reports:
            uploaded_at = format_datetime(r["UploadedAt"])
            patient_info = f"👤 **{r['PatientName']}** (`{r['PatientID']}`) - Case `{r['CaseID']}`"
            link = f"[📂 View Report]({r['URL']})"
            entry = {
                "display": f"{patient_info}  \n🕒 `{uploaded_at}` — {link}",
                "url": r['URL'],
                "patient_id": r['PatientID'],
                "case_id": r['CaseID'],
                "type": r['Type']
            }
            if r["Type"] == "lab":
                lab_reports.append(entry)
            elif r["Type"] == "scan":
                scan_reports.append(entry)
            elif r["Type"] == "prescription":  # This is what we set in the PDF generation
                clinical_insights.append(entry)
        # Create three columns instead of two
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("🧪 Lab Reports")
            if lab_reports:
                for report in lab_reports:
                    st.markdown(report["display"])
                    if st.button(f"🗑️ Delete", key=f"delete_lab_report_{report['url']}"):
                        # --- DEBUGGING INFORMATION ADDED HERE ---
                        st.info(f"Attempting to delete Lab Report URL: `{report['url']}`")
                        try:
                            # Delete from SeaweedFS
                            seaweed_response = requests.delete(report['url'])
                            if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                st.success(f"✅ File deleted from SeaweedFS: {report['url']}")
                            else:
                                st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: `{seaweed_response.status_code}`, Response: `{seaweed_response.text}`). Neo4j deletion only.")
                            # Delete from Neo4j
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "lab"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Lab report deleted from Neo4j!")
                            st.rerun()
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "lab"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Lab report deleted from Neo4j!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ An error occurred during deletion: {e}")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "lab"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Lab report deleted from Neo4j!")
                            st.rerun()
                    st.markdown("---")
            else:
                st.markdown("No lab reports uploaded yet.")
        with col2:
            st.subheader("🩻 Scan Reports")
            if scan_reports:
                for report in scan_reports:
                    st.markdown(report["display"])
                    if st.button(f"🗑️ Delete", key=f"delete_scan_report_{report['url']}"):
                        # --- DEBUGGING INFORMATION ADDED HERE ---
                        st.info(f"Attempting to delete Scan Report URL: `{report['url']}`")
                        try:
                            # Delete from SeaweedFS
                            seaweed_response = requests.delete(report['url'])
                            if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                st.success(f"✅ File deleted from SeaweedFS: {report['url']}")
                            else:
                                st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: `{seaweed_response.status_code}`, Response: `{seaweed_response.text}`). Neo4j deletion only.")
                            # Delete from Neo4j
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "scan"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Scan report deleted from Neo4j!")
                            st.rerun()
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "scan"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Scan report deleted from Neo4j!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ An error occurred during deletion: {e}")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "scan"})
                                    DETACH DELETE r
                                """, {"url": report['url']})
                            st.success("✅ Scan report deleted from Neo4j!")
                            st.rerun()
                    st.markdown("---")
            else:
                st.markdown("No scan reports uploaded yet.")
        with col3:
            st.subheader("📋 Generated Clinical Insights")
            if clinical_insights:
                for insight in clinical_insights:
                    st.markdown(insight["display"])
                    if st.button(f"🗑️ Delete", key=f"delete_clinical_insight_{insight['url']}"):
                        # --- DEBUGGING INFORMATION ADDED HERE ---
                        st.info(f"Attempting to delete Clinical Insight URL: `{insight['url']}`")
                        try:
                            # Delete from SeaweedFS
                            seaweed_response = requests.delete(insight['url'])
                            if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                st.success(f"✅ File deleted from SeaweedFS: {insight['url']}")
                            else:
                                st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: `{seaweed_response.status_code}`, Response: `{seaweed_response.text}`). Neo4j deletion only.")
                            # Delete from Neo4j
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                    DETACH DELETE r
                                """, {"url": insight['url']})
                            st.success("✅ Clinical Insight deleted from Neo4j!")
                            st.rerun()
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                    DETACH DELETE r
                                """, {"url": insight['url']})
                            st.success("✅ Clinical Insight deleted from Neo4j!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ An error occurred during deletion: {e}")
                            st.info("Attempting to delete from Neo4j only...")
                            with driver.session() as session:
                                session.run("""
                                    MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                    DETACH DELETE r
                                """, {"url": insight['url']})
                            st.success("✅ Clinical Insight deleted from Neo4j!")
                            st.rerun()
                    st.markdown("---")
            else:
                st.info("No clinical insights generated yet.")
    else:
        st.info("ℹ️ No reports or insights have been generated yet.")


    if st.button("🔄 Refresh Cases from Database"):
        st.rerun()

    if cases: # This 'if cases' block remains for the individual case expanders
        st.markdown("### 📤 Upload Reports for Assigned Cases")
        for case in cases:
            with st.expander(f"Case {case['CaseID']} – {case['PatientName']}"):

                # --------- Upload Reports ------------
                st.write("Upload Lab Reports (CSV, PDF) or Radiology Images (JPG, PNG, DICOM)")

                lab_file = st.file_uploader(
                    f"Upload Lab Report (CSV or PDF) for {case['CaseID']}",
                    type=["csv", "pdf"],
                    key=f"lab_{case['CaseID']}"
                )

                scan_file = st.file_uploader(
                    f"Upload Radiology Scan (JPG, PNG, DICOM) for {case['CaseID']}",
                    type=["jpg", "jpeg", "png", "dcm"],
                    key=f"scan_{case['CaseID']}"
                )

                def upload_to_seaweed(file, filename):
                    import requests
                    files = {'file': (filename, file)}
                    res = requests.post("http://localhost:8888/seaweedfs/" + filename, files=files)
                    if res.status_code == 201:
                        return f"http://localhost:8888/seaweedfs/{filename}"
                    return None

                if lab_file and st.button(f"Submit Lab Report", key=f"lab_submit_{case['CaseID']}"):
                    file_url = upload_to_seaweed(lab_file, f"{case['CaseID']}_lab_{lab_file.name}")
                    if file_url:
                        with driver.session() as session:
                            session.run("""
                                MATCH (c:Case {case_id: $case_id})-[:BELONGS_TO]->(p:Patient)
                                CREATE (r:UploadedReport {url: $url, type: "lab", uploaded_at: datetime()})
                                MERGE (c)-[:HAS_REPORT]->(r)
                                MERGE (p)-[:HAS_UPLOADED]->(r)
                            """, {
                                "case_id": case["CaseID"],
                                "url": file_url
                            })
                        st.success("✅ Lab Report uploaded and linked to both Case and Patient.")
                        st.rerun()

                if scan_file and st.button(f"Submit Radiology Scan", key=f"scan_submit_{case['CaseID']}"):
                    file_url = upload_to_seaweed(scan_file, f"{case['CaseID']}_scan_{scan_file.name}")
                    if file_url:
                        with driver.session() as session:
                            session.run("""
                                MATCH (c:Case {case_id: $case_id})-[:BELONGS_TO]->(p:Patient)
                                CREATE (r:UploadedReport {url: $url, type: "scan", uploaded_at: datetime()})
                                MERGE (c)-[:HAS_REPORT]->(r)
                                MERGE (p)-[:HAS_UPLOADED]->(r)
                            """, {
                                "case_id": case["CaseID"],
                                "url": file_url
                            })
                        st.success("✅ Scan uploaded and linked to both Case and Patient.")
                        st.rerun()


                # ---- View or Update Summary Mode ----
                summary_mode = st.radio(
                    f"🧾 Summary View for Case {case['CaseID']}",
                    ["📖 View Saved Summary", "✍️ Update Summary"],
                    key=f"summary_mode_{case['CaseID']}"
                )
                if summary_mode == "📖 View Saved Summary":
                    with driver.session() as session:
                        result = session.run("""
                            MATCH (c:Case {case_id: $case_id})
                            RETURN c.case_summary AS summary
                        """, {"case_id": case["CaseID"]})
                        record = result.single()
                        saved_summary = record["summary"] if record and record["summary"] else "⚠️ No summary saved yet."
                    st.text_area("📄 Saved Summary", value=saved_summary, height=200, disabled=True)


                # ---- Summary Input Mode: Toggle Between Typing and Mic ----
                st.markdown("### 📝 Add Case Summary")
                mode = st.radio("Choose input mode", ["🧾 Type Summary", "🎤 Dictate with Mic"], key=f"input_mode_{case['CaseID']}")
                if mode == "🧾 Type Summary":
                    typed_summary = st.text_area("Enter case summary manually", height=150, key=f"typed_summary_{case['CaseID']}")
                    if st.button("💾 Save Typed Summary", key=f"save_typed_{case['CaseID']}"):
                        with driver.session() as session:
                            session.run("""
                                MATCH (c:Case {case_id: $case_id})
                                SET c.case_summary = $summary,
                                    c.modified_at = datetime()
                            """, {"case_id": case["CaseID"], "summary": typed_summary})

                        st.success("📝 Summary saved to Neo4j.")
                        st.rerun()
                elif mode == "🎤 Dictate with Mic":
                    import whisper
                    import tempfile
                    import os
                    audio = audiorecorder("🎤 Click to Record", "🛑 Stop Recording", key=f"audio_recorder_{case['CaseID']}")
                    if len(audio) > 0:
                        st.audio(audio.export().read(), format="audio/wav")
                        if st.button("📝 Transcribe & Save", key=f"mic_save_{case['CaseID']}"):
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                                audio.export(tmp.name, format="wav")
                                temp_path = tmp.name
                            with st.spinner("Transcribing..."):
                                model = whisper.load_model("base")
                                result = model.transcribe(temp_path)
                                os.remove(temp_path)
                                transcription = result["text"]
                                st.json(result)
                            st.success("✅ Transcription complete!")
                            st.text_area("🧾 Transcribed Summary", value=transcription, height=150)
                            with driver.session() as session:
                                session.run("""
                                MATCH (c:Case {case_id: $case_id})
                                SET c.case_summary = $summary,
                                    c.modified_at = datetime()
                            """, {"case_id": case["CaseID"], "summary": transcription})
                            st.success("📝 Summary saved to Neo4j.")
                            st.rerun()
                # ---- Uploaded Files for this Case ----
                with driver.session() as session:
                    result = session.run("""
                        MATCH (c:Case {case_id: $case_id})-[:HAS_REPORT]->(r:UploadedReport)
                        RETURN r.url AS url, r.type AS type, r.uploaded_at AS uploaded_at
                        ORDER BY r.uploaded_at DESC
                    """, {"case_id": case["CaseID"]})
                    report_records = result.data()
                if report_records:
                    st.markdown("### 📂 All Reports for This Case")
                    # Separate reports by type
                    lab_reports = [r for r in report_records if r["type"] == "lab"]
                    scan_reports = [r for r in report_records if r["type"] == "scan"]
                    clinical_insights = [r for r in report_records if r["type"] == "prescription"]
                    # Display in organized sections
                    report_cols = st.columns(3)
                    # Lab Reports Column
                    with report_cols[0]:
                        st.markdown("#### 🧪 Lab Reports")
                        if lab_reports:
                            for report in lab_reports:
                                file_url = report["url"]
                                uploaded_at = format_datetime(report.get("uploaded_at"))
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Lab Report]({file_url})")
                                if st.button(f"🗑️ Delete", key=f"delete_case_lab_report_{file_url}"):
                                    try:
                                        # Delete from SeaweedFS
                                        seaweed_response = requests.delete(file_url)
                                        if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                            st.success(f"✅ File deleted from SeaweedFS: {file_url}")
                                        else:
                                            st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: {seaweed_response.status_code}). Neo4j deletion only.")
                                        # Delete from Neo4j
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "lab"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Lab report deleted from Neo4j!")
                                        st.rerun()
                                    except requests.exceptions.ConnectionError:
                                        st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                                        st.info("Attempting to delete from Neo4j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "lab"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Lab report deleted from Neo4j!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ An error occurred during deletion: {e}")
                                        st.info("Attempting to delete from Neo44j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "lab"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Lab report deleted from Neo4j!")
                                        st.rerun()
                                st.markdown("---")
                        else:
                            st.info("No lab reports")
                    # Scan Reports Column
                    with report_cols[1]:
                        st.markdown("#### 🩻 Scan Reports")
                        if scan_reports:
                            for report in scan_reports:
                                file_url = report["url"]
                                uploaded_at = format_datetime(report.get("uploaded_at"))
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Scan]({file_url})")
                                if st.button(f"🗑️ Delete", key=f"delete_case_scan_report_{file_url}"):
                                    try:
                                        # Delete from SeaweedFS
                                        seaweed_response = requests.delete(file_url)
                                        if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                            st.success(f"✅ File deleted from SeaweedFS: {file_url}")
                                        else:
                                            st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: {seaweed_response.status_code}). Neo4j deletion only.")
                                        # Delete from Neo4j
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "scan"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Scan report deleted from Neo4j!")
                                        st.rerun()
                                    except requests.exceptions.ConnectionError:
                                        st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                                        st.info("Attempting to delete from Neo4j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "scan"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Scan report deleted from Neo4j!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ An error occurred during deletion: {e}")
                                        st.info("Attempting to delete from Neo4j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "scan"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Scan report deleted from Neo4j!")
                                        st.rerun()
                                st.markdown("---")
                        else:
                            st.info("No scan reports")
                    # Clinical Insights Column
                    with report_cols[2]:
                        st.markdown("#### 📋 Clinical Insights")
                        if clinical_insights:
                            for insight in clinical_insights:
                                file_url = insight["url"]
                                uploaded_at = format_datetime(insight.get("uploaded_at"))
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Insight PDF]({file_url})")
                                if st.button(f"🗑️ Delete", key=f"delete_case_clinical_insight_{file_url}"):
                                    try:
                                        # Delete from SeaweedFS
                                        seaweed_response = requests.delete(file_url)
                                        if seaweed_response.status_code == 200 or seaweed_response.status_code == 204:
                                            st.success(f"✅ File deleted from SeaweedFS: {file_url}")
                                        else:
                                            st.warning(f"⚠️ Failed to delete file from SeaweedFS (Status: {seaweed_response.status_code}). Neo4j deletion only.")
                                        # Delete from Neo4j
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Clinical Insight deleted from Neo4j!")
                                        st.rerun()
                                    except requests.exceptions.ConnectionError:
                                        st.error("❌ Could not connect to SeaweedFS. Please ensure it is running.")
                                        st.info("Attempting to delete from Neo4j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Clinical Insight deleted from Neo4j!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ An error occurred during deletion: {e}")
                                        st.info("Attempting to delete from Neo4j only...")
                                        with driver.session() as session_delete:
                                            session_delete.run("""
                                                MATCH (r:UploadedReport {url: $url, type: "prescription"})
                                                DETACH DELETE r
                                            """, {"url": file_url})
                                        st.success("✅ Clinical Insight deleted from Neo4j!")
                                        st.rerun()
                                st.markdown("---")
                        else:
                            st.info("No insights generated")
                else:
                    st.info("ℹ️ No reports uploaded for this case.")
                # --- Run Multimodal Gemini Agent ---
                st.markdown("### 🤖 Generate AI Clinical Insight")
                if st.button(f"💡 Generate Multimodal Insight", key=f"gen_insight_{case['CaseID']}"):
                    # with st.spinner("🧠 Analyzing case with Gemini 2.5 Flash..."):
                    
                        # 1. Fetch saved summary from Neo4j

                        with driver.session() as session:
                            result = session.run("""
                                MATCH (c:Case {case_id: $case_id})
                                RETURN c.case_summary AS summary
                            """, {"case_id": case["CaseID"]})
                            record = result.single()
                            saved_summary_from_db = record["summary"] if record and record["summary"] else "" # Renamed var

                        # 2. Fetch latest lab & scan reports from UploadedReport nodes

                        with driver.session() as session:
                            result = session.run("""
                                MATCH (c:Case {case_id: $case_id})-[:HAS_REPORT]->(r:UploadedReport)
                                RETURN r.url AS url, r.type AS type, r.uploaded_at AS uploaded_at
                                ORDER BY r.uploaded_at DESC
                            """, {"case_id": case["CaseID"]})
                            reports_for_agent = result.data() # Renamed var
                        latest_lab = next((r for r in reports_for_agent if r["type"] == "lab"), None)
                        latest_scan = next((r for r in reports_for_agent if r["type"] == "scan"), None)
                        import requests
                        from io import BytesIO
                        lab_data = None
                        scan_image = None
                        # 3. Load and parse lab report (CSV or PDF)
                        
                        if latest_lab:
                            try:
                                response = requests.get(latest_lab["url"])
                                if response.ok:
                                    file = BytesIO(response.content)
                                    file.name = latest_lab["url"].split("/")[-1]
                                    lab_data = parse_lab_file(file)
                                else:
                                    st.warning("⚠️ Couldn't fetch the lab report file.")
                            except Exception as e:
                                st.error(f"⚠️ Failed to load lab report: {e}")
                        # 4. Load scan image and encode
                        import pydicom
                        import matplotlib.pyplot as plt
                        from PIL import Image
                        import io

                        scan_image = None
                        scan_description = None

                        if latest_scan:
                            try:
                                response = requests.get(latest_scan["url"])
                                if response.ok:
                                    file_content = response.content
                                    # Check if it's a DICOM file
                                    if file_content[128:132] == b'DICM':
                                        dicom_file = BytesIO(file_content)
                                        ds = pydicom.dcmread(dicom_file)

                                        # Convert pixel array to a PIL image
                                        img = Image.fromarray(ds.pixel_array).convert("L")  # Grayscale
                                        buffered = io.BytesIO()
                                        img.save(buffered, format="PNG")
                                        buffered.seek(0)

                                        scan_image = encode_image(buffered)
                                        scan_description = "Radiology scan (DICOM) image attached."
                                    else:
                                        # Treat as standard image (jpg, jpeg, png)
                                        scan_image = encode_image(BytesIO(file_content))
                                        scan_description = "Radiology scan (image) attached."
                                else:
                                    st.warning("⚠️ Couldn't fetch the scan image file.")
                            except Exception as e:
                                st.error(f"⚠️ Failed to load scan file: {e}")


                        # 5. Build multimodal prompt & call Gemini
                        prompt = build_multimodal_prompt(saved_summary_from_db, lab_data, scan_description if scan_image else None)

                        # 6. Run Gemini Agent and Show Result
                        st.markdown("## 🧾 Gemini AI Output")

                        # Call Gemini once and also generate PDF
                        with st.spinner("💬 Generating clinical insight with Gemini..."):
                            result = call_gemini(prompt, images=[scan_image] if scan_image else [], case_id=case["CaseID"], doctor_id=doctor_id)
                            gemini_text = result["text"]
                            pdf_url = result["pdf_url"]

                            if not gemini_text or gemini_text.startswith("❌"):
                                st.error(gemini_text)
                            else:
                                # Display all sections
                                sections = gemini_text.split("### ")
                                for idx, section in enumerate(sections):
                                    if not section.strip():
                                        continue
                                    lines = section.strip().splitlines()
                                    if not lines:
                                        continue
                                    title = lines[0].strip(":").strip()
                                    content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                                    # Handle different sections with appropriate icons and formatting
                                    title_lower = title.lower()
                                    if "soap note" in title_lower:
                                        st.markdown(f"### 🩺 **{title}**")
                                        st.markdown(content)
                                    elif "differential diagnos" in title_lower:
                                        st.markdown(f"### 🧠 **{title}**")
                                        st.markdown(content)
                                    elif "recommended investigation" in title_lower or "investigation" in title_lower:
                                        st.markdown(f"### 🔬 **{title}**")
                                        st.markdown(content)
                                    elif "treatment" in title_lower:
                                        st.markdown(f"### 💊 **{title}**")
                                        st.markdown(content)
                                    elif "file interpretation" in title_lower:
                                        st.markdown("### 📂 **File Interpretations**")
                                        st.markdown(content)
                                    elif "confidence" in title_lower:
                                        # Simplified confidence score handling
                                        if content.strip():
                                            # Extract numeric confidence if present
                                            confidence_match = re.search(r'(\d+(?:\.\d+)?%?)', content)
                                            if confidence_match:
                                                confidence_value = confidence_match.group(1)
                                                st.success(f"✅ **Confidence Score:** {confidence_value}")
                                            else:
                                                st.success(f"✅ **Confidence Score:** {content}")
                                        else:
                                            # If no content, try to find it in the title itself
                                            confidence_match = re.search(r'(\d+(?:\.\d+)?%?)', title)
                                            if confidence_match:
                                                confidence_value = confidence_match.group(1)
                                                st.success(f"✅ **Confidence Score:** {confidence_value}")
                                            else:
                                                st.info("ℹ️ Confidence score not provided.")
                                    else:
                                        # Generic section
                                        st.markdown(f"### 📋 **{title}**")
                                        if content:
                                            st.markdown(content)
                                        else:
                                            st.info("No additional details provided for this section.")

                                            
                                # 7. Save PDF URL in Neo4j + Show Download Button
                                if pdf_url:
                                    with driver.session() as session:
                                        session.run("""
                                            MATCH (c:Case {case_id: $case_id})-[:BELONGS_TO]->(p:Patient)
                                            CREATE (r:UploadedReport {
                                                url: $url,
                                                type: "prescription",
                                                uploaded_at: datetime()
                                            })
                                            MERGE (c)-[:HAS_REPORT]->(r)
                                            MERGE (p)-[:HAS_UPLOADED]->(r)
                                        """, {"case_id": case["CaseID"], "url": pdf_url})
                                    st.success("✅ Clinical Insight PDF exported, uploaded, and saved in Neo4j!")
                                    st.markdown(f"🔗 [⬇️ Click to Download Clinical Insight PDF]({pdf_url})")
                                else:
                                    st.warning("⚠️ Clinical Insight PDF export failed. Please try again.")

                # Add feedback section - store in session state to persist across reruns
                feedback_key = f"show_feedback_{case['CaseID']}"
                good_key = f"good_clicked_{case['CaseID']}"
                bad_key = f"bad_clicked_{case['CaseID']}"
                dismiss_key = f"dismiss_clicked_{case['CaseID']}"
                
                if feedback_key not in st.session_state:
                    st.session_state[feedback_key] = True

                # Check for button clicks first (before showing buttons)
                if st.session_state.get(good_key, False):
                    store_feedback_to_file(case["CaseID"], doctor_id, "good")
                    st.success("✅ Thank you for your positive feedback!")
                    # st.session_state[feedback_key] = False
                    st.session_state[good_key] = False
                    
                elif st.session_state.get(bad_key, False):
                    store_feedback_to_file(case["CaseID"], doctor_id, "bad")
                    st.success("✅ Thank you for your feedback! We'll work to improve.")
                    # st.session_state[feedback_key] = False
                    st.session_state[bad_key] = False
                    
                elif st.session_state.get(dismiss_key, False):
                    # st.session_state[feedback_key] = False
                    st.session_state[dismiss_key] = False

                # Show feedback buttons only if still active
                if st.session_state.get(feedback_key, False):
                    st.markdown("---")
                    st.markdown("### 📊 Was this insight helpful?")
                    col_good, col_bad, col_dismiss = st.columns(3)
                    with col_good:
                        if st.button("👍 Good Response", key=f"good_feedback_{case['CaseID']}"):
                            st.session_state[good_key] = True
                            # st.rerun()
                    with col_bad:
                        if st.button("👎 Poor Response", key=f"bad_feedback_{case['CaseID']}"):
                            st.session_state[bad_key] = True
                            # st.rerun()
                    with col_dismiss:
                        if st.button("❌ Dismiss", key=f"dismiss_feedback_{case['CaseID']}"):
                            st.session_state[dismiss_key] = True
                            # st.rerun()  # Remove feedback buttons
                                            
                                    
    else:
        st.info("No cases assigned to you yet.")


    if st.button("Logout"):
        del st.session_state.logged_in_doctor
        st.rerun()