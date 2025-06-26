import streamlit as st
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import pandas as pd
from audiorecorder import audiorecorder
from agents.prompt_builder import build_multimodal_prompt
from agents.file_parser import parse_lab_file, encode_image
from agents.gemini_agent import call_gemini
from agents.pdf_exporter import generate_pdf_and_save
from datetime import datetime, date # Import datetime and date for filtering
from dateutil import parser
import pytz


# --------- Date-Time Parser --------------------
def format_datetime(datetime_value):
    """
    Centralized datetime formatting function
    Handles various datetime formats and returns a consistent display format
    """
    if not datetime_value:
        return "Unknown"
    
    try:
        from dateutil import parser
        import pytz
        from datetime import datetime # Re-import datetime in case it's shadowed elsewhere
        
        # Handle different datetime formats
        if isinstance(datetime_value, str):
            dt = parser.isoparse(datetime_value)
        else:
            dt = datetime_value # Corrected line
        
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
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap');

/* --- Base Styles --- */
html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 16px; /* Slightly increased for better readability */
    background: #F8F9FA; /* Light grey background for a softer feel */
    color: #343A40; /* Darker text for better contrast */
    line-height: 1.6;
}

/* --- Headings --- */
h1, h2, h3, h4, h5, h6 {
    font-weight: 700;
    color: #495057; /* Slightly darker than body text for emphasis */
    margin-bottom: 0.75rem; /* Increased spacing below headings */
    margin-top: 1.5rem; /* Spacing above headings */
    letter-spacing: 0.01em;
}
h1 { font-size: 2.5em; } /* Relative units for better scaling */
h2 { font-size: 2em; }
h3 { font-size: 1.75em; }

/* --- Buttons --- */
.stButton > button {
    background: #AA336A; /* Muted primary color */
    color: #fff;
    border: none;
    border-radius: 8px; /* Slightly more rounded */
    padding: 0.6rem 1.5rem; /* Increased padding */
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease-in-out; /* Smooth transition for all properties */
    box-shadow: 0 2px 8px rgba(0,0,0,0.1); /* Softer shadow */
}
.stButton > button:hover {
    background: #495057; /* Darker on hover */
    transform: translateY(-1px); /* Slight lift effect */
    box_shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* --- Inputs and Labels --- */
.stTextInput > label,
.stSelectbox > label,
.stRadio > label,
.stCheckbox > label { /* Added checkbox label */
    font-weight: 600;
    color: #495057;
    margin_bottom: 0.5rem; /* Consistent spacing */
    display: block;
}
.stTextInput input,
.stSelectbox div[data-baseweb="select"],
.stNumberInput input { /* Added number input */
    border: 1px solid #CED4DA; /* Softer border color */
    border_radius: 8px; /* Consistent rounded corners */
    padding: 0.6rem 1rem;
    background: #FFFFFF; /* White background for inputs */
    color: #343A40;
    font_size: 1em; /* Relative font size */
    box_shadow: inset 0 1px 3px rgba(0,0,0,0.05); /* Subtle inner shadow */
    transition: border-color 0.2s, box_shadow 0.2s;
}
.stTextInput input:focus,
.stSelectbox div[data-baseweb="select"]:focus-within,
.stNumberInput input:focus {
    border_color: #6C757D; /* Highlight on focus */
    box_shadow: 0 0 0 0.2rem rgba(108, 117, 125, 0.25); /* Focus ring */
    outline: none; /* Remove default outline */
}

/* --- DataFrame/Table Styling --- */
.stDataFrame {
    border: 1px solid #E9ECEF; /* Lighter border */
    border_radius: 10px; /* More pronounced rounded corners */
    overflow: hidden;
    margin_bottom: 1.5rem; /* More spacing */
    box_shadow: 0 4px 12px rgba(0,0,0,0.08); /* Added shadow for depth */
}
.stDataFrame th {
    background: #6C757D; /* Consistent header color */
    color: #fff !important;
    font_weight: 600;
    padding: 0.8rem 1rem; /* Increased padding */
    text_align: left;
}
.stDataFrame td {
    color: #343A40 !important;
    padding: 0.8rem 1rem;
    background: #fff;
    border_bottom: 1px solid #F1F3F5; /* Subtle row separator */
}
.stDataFrame tr:last-child td {
    border_bottom: none; /* No border for the last row */
}

/* --- Expander and Block Container --- */
.block-container {
    padding: 2rem 2.5rem; /* More generous padding for content */
    max_width: 1200px; /* Optional: Set a max-width for better layout on large screens */
    margin: 0 auto; /* Center the content */
}
.stExpander {
    border_radius: 10px !important; /* Consistent rounded corners */
    border: 1px solid #E9ECEF !important;
    margin_bottom: 1.5rem;
    box_shadow: 0 2px 8px rgba(0,0,0,0.05); /* Soft shadow */
    background_color: #483248; /* White background for expander */
}

/* --- Miscellaneous Spacing & Elements --- */
hr {
    border: none;
    border_top: 1px solid #DEE2E6; /* Lighter separator line */
    margin: 2.5rem 0; /* More vertical space around HR */
}

/* Specific adjustments for Streamlit's internal elements */
div[data-testid="stSidebar"] {
    background_color: #FFFFFF; /* White sidebar */
    box_shadow: 2px 0 8px rgba(0,0,0,0.05); /* Subtle shadow for sidebar */
    padding_top: 2rem;
}

div[data-testid="stVerticalBlock"] {
    gap: 1.5rem; /* Adjust vertical spacing between elements */
}

div[data-testid="stHorizontalBlock"] {
    gap: 1.5rem; /* Adjust horizontal spacing between elements */
}

/* Ensure text elements inherit base font size */
.stMarkdown p, .stMarkdown li, .stMarkdown div, .stMarkdown span {
    font_size: 1em !important;
}

</style>
""", unsafe_allow_html=True)


# -------- Utility Functions --------
def clear_new_case_inputs():
    """Clears the session state values for the new case input fields."""
    if "new_patient_id_input" in st.session_state:
        st.session_state["new_patient_id_input"] = ""
    if "new_patient_name_input" in st.session_state:
        st.session_state["new_patient_name_input"] = ""
    if "new_case_id_input" in st.session_state:
        st.session_state["new_case_id_input"] = ""
    if "new_case_summary_input" in st.session_state:
        st.session_state["new_case_summary_input"] = ""


def add_new_case_to_neo4j(driver, patient_id, patient_name, case_id, case_summary, doctor_id):
    """
    Adds a new case and patient (if new) to Neo4j,
    linked to the specified doctor.
    """
    try:
        with driver.session() as session:
            # First, check if the provided case_id already exists
            existing_case = session.run("MATCH (c:Case {case_id: $case_id}) RETURN c", {"case_id": case_id}).single()
            if existing_case:
                return False, f"Case ID '{case_id}' already exists. Please choose a unique Case ID for a new case."

            # If case_id is unique, proceed to create nodes and relationships
            session.run(
                """
                MERGE (d:Doctor {id: $doctor_id}) // Ensure doctor exists or create if not (should exist from login)

                MERGE (p:Patient {id: $patient_id}) // Create Patient if new, or use existing if ID matches
                ON CREATE SET p.name = $patient_name // Only set name if patient is newly created

                CREATE (c:Case {case_id: $case_id}) // Create a new Case node (ensured unique by check above)
                SET c.case_summary = $case_summary,
                    c.created_at = datetime() // Set creation timestamp

                MERGE (d)-[:HANDLES]->(c) // Link Doctor to Case
                MERGE (c)-[:BELONGS_TO]->(p) // Link Case to Patient
                """,
                {
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "case_id": case_id,
                    "case_summary": case_summary
                }
            )
        return True, "✅ New case added successfully!"
    except Exception as e:
        return False, f"❌ An error occurred while adding the case: {e}"

def delete_case_from_neo4j(driver, case_id):
    """
    Deletes a case and all its associated relationships, uploaded reports, and feedback from Neo4j.
    Does NOT delete the patient or doctor if they are associated with other cases.
    """
    try:
        with driver.session() as session:
            # Query to find related report URLs to delete from SeaweedFS
            report_urls = session.run(
                """
                MATCH (c:Case {case_id: $case_id})-[r_rel:HAS_REPORT]->(ur:UploadedReport)
                RETURN ur.url AS url
                """, {"case_id": case_id}
            ).data()

            # Delete files from SeaweedFS if they exist
            if report_urls:
                import requests
                for record in report_urls:
                    file_url = record["url"]
                    filename = file_url.split("/")[-1]
                    try:
                        delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                        if delete_res.ok:
                            st.info(f"🗑️ Deleted file from SeaweedFS: {filename}")
                        else:
                            st.warning(f"⚠️ Failed to delete file {filename} from SeaweedFS (Status: {delete_res.status_code}).")
                    except Exception as e:
                        st.error(f"❌ Error deleting file {filename} from SeaweedFS: {e}")

            # Cypher query to delete the case node and all its relationships
            # DETACH DELETE handles all relationships connected to 'c'
            # Also explicitly delete related UploadedReport and Feedback nodes that are only linked to this case.
            session.run(
                """
                MATCH (c:Case {case_id: $case_id})
                OPTIONAL MATCH (c)-[rel_report:HAS_REPORT]->(ur:UploadedReport)
                OPTIONAL MATCH (c)-[rel_feedback:HAS_FEEDBACK]->(f:Feedback)
                DETACH DELETE c, ur, f
                """,
                {"case_id": case_id}
            )
        return True, f"✅ Case '{case_id}' and its associated data deleted successfully!"
    except Exception as e:
        return False, f"❌ An error occurred while deleting case '{case_id}': {e}"


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

def fetch_feedback_summary():
    """
    Fetches the total count of good and poor responses from Neo4j.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (f:Feedback)
            RETURN f.is_good_response AS is_good, COUNT(f) AS count
            ORDER BY is_good DESC
        """)
        summary = {"good": 0, "poor": 0}
        for record in result:
            if record["is_good"]:
                summary["good"] = record["count"]
            else:
                summary["poor"] = record["count"]
        return summary


# -------- Streamlit App UI --------
st.markdown("# 🩺 Multimodal Clinical Insight Assistant")

# Show login/registration if not logged in
if "logged_in_doctor" not in st.session_state:

    doctors = fetch_all_doctors()
    doctor_df = pd.DataFrame(doctors)
    st.markdown("### 👩‍⚕️ Approved Doctors")
    st.dataframe(doctor_df.rename(columns={"id": "Doctor ID", "name": "Name", "Specialization": "Role"}), use_container_width=True) # Changed "role" to "Specialization" for display

    tabs = st.tabs(["Login", "Register"])

    with tabs[0]:
        st.subheader("Login")
        login_id = st.text_input("Doctor ID")
        login_password = st.text_input("Password", type="password")
        if st.button("Login"):
            with driver.session() as session:
                registered = session.run("MATCH (d:DoctorLogin {id: $doctor_id}) RETURN d", {"doctor_id": login_id}).single()

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
            # Create a list of dictionaries with CaseID and a delete button for each
            cases_with_buttons = []
            for index, row in filtered_df.iterrows():
                case_id = row['CaseID']
                patient_id = row['PatientID']
                patient_name = row['PatientName']
                summary = row['Summary']
                created_at = row['CreatedAt']

                # Use a unique key for each delete button based on case_id
                delete_button_key = f"delete_case_{case_id}"

                col_case, col_delete = st.columns([0.9, 0.1])
                with col_case:
                    st.markdown(f"**Case ID:** {case_id}")
                    st.markdown(f"**Patient ID:** {patient_id}")
                    st.markdown(f"**Patient Name:** {patient_name}")
                    st.markdown(f"**Summary:** {summary}")
                    st.markdown(f"**Created At:** {created_at}")
                with col_delete:
                    # Place a small delete button
                    if st.button("🗑️", key=delete_button_key):
                        # Confirmation dialog (using Streamlit's trick since confirm() is not allowed)
                        st.session_state['confirm_delete_case_id'] = case_id
                        st.warning(f"Are you sure you want to delete Case '{case_id}'? This action cannot be undone. \n\n Click 'Confirm Delete' below to proceed.")
                st.markdown("---") # Separator between cases

            # Confirmation for delete action (outside the loop, after all buttons are rendered)
            if 'confirm_delete_case_id' in st.session_state and st.session_state['confirm_delete_case_id']:
                case_id_to_delete = st.session_state['confirm_delete_case_id']
                if st.button(f"Confirm Delete Case '{case_id_to_delete}'", key=f"confirm_delete_{case_id_to_delete}"):
                    success, message = delete_case_from_neo4j(driver, case_id_to_delete)
                    if success:
                        st.success(message)
                        del st.session_state['confirm_delete_case_id'] # Clear confirmation state
                        st.rerun()
                    else:
                        st.error(message)
                if st.button(f"Cancel Delete", key=f"cancel_delete_{case_id_to_delete}"):
                    st.info("Case deletion cancelled.")
                    del st.session_state['confirm_delete_case_id'] # Clear confirmation state
                    st.rerun()

        else:
            st.info("No cases match your current filters.")

        st.markdown("---") # Separator


        st.markdown("## ➕ Add New Patient Case")
        with st.expander("Add a new case for a new or existing patient"):
            # Use st.session_state for inputs to allow clearing them after submission
            new_patient_id = st.text_input("Patient ID (e.g., P013)", key="new_patient_id_input", 
                                        value=st.session_state.get("new_patient_id_input", ""))
            new_patient_name = st.text_input("Patient Name (e.g., Jane Doe)", key="new_patient_name_input",
                                            value=st.session_state.get("new_patient_name_input", ""))
            new_case_id = st.text_input("New Case ID (must be unique, e.g., C013)", key="new_case_id_input",
                                        value=st.session_state.get("new_case_id_input", ""))
            new_case_summary = st.text_area("Case Summary", height=100, key="new_case_summary_input",
                                            value=st.session_state.get("new_case_summary_input", ""))

            if st.button("Submit New Case", key="submit_new_case_btn"):
                if not all([new_patient_id, new_patient_name, new_case_id, new_case_summary]):
                    st.warning("⚠️ Please fill in all fields to add a new case.")
                else:
                    # Use the logged-in doctor's ID
                    logged_in_doctor_id = st.session_state.logged_in_doctor
                    
                    success, message = add_new_case_to_neo4j(
                        driver,
                        new_patient_id.strip(), # .strip() to remove leading/trailing whitespace
                        new_patient_name.strip(),
                        new_case_id.strip(),
                        new_case_summary.strip(),
                        logged_in_doctor_id
                    )
                    if success:
                        st.success(message)
                        # Clear inputs after successful submission
                        clear_new_case_inputs() # Call the new clearing function here
                        st.rerun() # Refresh the page to show the new case in the 'Assigned Cases' table
                    else:
                        st.error(message)

        st.markdown("---") # Another separator after the new case section


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
                    
                    # st.code(result['query'], language='cypher') # Uncomment for debugging Cypher query
                    
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
            filename = r['URL'].split("/")[-1]
            
            # Create entry with delete button data
            entry = {
                "display": f"{patient_info}  \n🕒 `{uploaded_at}` — {link}",
                "url": r['URL'],
                "filename": filename,
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
                    
                    # Delete button for lab reports
                    if st.button(f"🗑️ Delete Lab Report", key=f"del_lab_{report['filename']}"):
                        try:
                            import requests
                            delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{report['filename']}")
                            if delete_res.ok:
                                with driver.session() as session:
                                    session.run("""
                                        MATCH (r:UploadedReport {url: $url})
                                        OPTIONAL MATCH (r)<-[rel]-()
                                        DELETE rel, r
                                    """, {"url": report["url"]})
                                st.success("✅ Lab Report deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("⚠️ Failed to delete file from SeaweedFS.")
                        except Exception as e:
                            st.error(f"❌ Error deleting Lab Report: {e}")
                    
                    st.markdown("---")
            else:
                st.markdown("No lab reports uploaded yet.")

        with col2:
            st.subheader("🩻 Scan Reports")
            if scan_reports:
                for report in scan_reports:
                    st.markdown(report["display"])
                    
                    # Delete button for scan reports
                    if st.button(f"🗑️ Delete Scan Report", key=f"del_scan_{report['filename']}"):
                        try:
                            import requests
                            delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{report['filename']}")
                            if delete_res.ok:
                                with driver.session() as session:
                                    session.run("""
                                        MATCH (r:UploadedReport {url: $url})
                                        OPTIONAL MATCH (r)<-[rel]-()
                                        DELETE rel, r
                                    """, {"url": report["url"]})
                                st.success("✅ Scan Report deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("⚠️ Failed to delete file from SeaweedFS.")
                        except Exception as e:
                            st.error(f"❌ Error deleting Scan Report: {e}")
                    
                    st.markdown("---")
            else:
                st.markdown("No scan reports uploaded yet.")

        with col3:
            st.subheader("📋 Generated Clinical Insights")
            if clinical_insights:
                for insight in clinical_insights:
                    st.markdown(insight["display"])
                    
                    # Delete button for clinical insights
                    if st.button(f"🗑️ Delete Clinical Insight", key=f"del_insight_{insight['filename']}"):
                        try:
                            import requests
                            delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{insight['filename']}")
                            if delete_res.ok:
                                with driver.session() as session:
                                    session.run("""
                                        MATCH (r:UploadedReport {url: $url})
                                        OPTIONAL MATCH (r)<-[rel]-()
                                        DELETE rel, r
                                    """, {"url": insight["url"]})
                                st.success("✅ Clinical Insight deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("⚠️ Failed to delete file from SeaweedFS.")
                        except Exception as e:
                            st.error(f"❌ Error deleting Clinical Insight: {e}")
                    
                    st.markdown("---")
            else:
                st.info("No clinical insights generated yet.")
    else:
        st.info("ℹ️ No reports or insights have been generated yet.")

    # -------- Feedback Dashboard --------
    st.markdown("## ✨ Feedback Dashboard")
    feedback_summary = fetch_feedback_summary()
    st.markdown(f"**👍 Good Responses:** {feedback_summary['good']}")
    st.markdown(f"**👎 Poor Responses:** {feedback_summary['poor']}")
    if feedback_summary['good'] + feedback_summary['poor'] > 0:
        total_feedback = feedback_summary['good'] + feedback_summary['poor']
        good_percentage = (feedback_summary['good'] / total_feedback) * 100
        poor_percentage = (feedback_summary['poor'] / total_feedback) * 100
        st.info(f"Overall satisfaction: {good_percentage:.1f}% positive ({total_feedback} total feedback points)")
    else:
        st.info("No feedback recorded yet.")

    st.markdown("---") # Separator

    if st.button("🔄 Refresh Cases from Database"):
        st.rerun()

    if cases: # This 'if cases' block remains for the individual case expanders
        st.markdown("### 📤 Upload Reports for Assigned Cases")

        for case in cases:
            with st.expander(f"Case {case['CaseID']} – {case['PatientName']}"):

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
                    # continue


                # ---- Summary Input Mode: Toggle Between Typing and Mic ----
                st.markdown("### 📝 Add Case Summary")

                mode = st.radio("Choose input mode", ["🧾 Type Summary", "🎤 Dictate with Mic"], key=f"input_mode_{case['CaseID']}")

                if mode == "🧾 Type Summary":
                    typed_summary = st.text_area("Enter case summary manually", height=150, key=f"typed_summary_{case['CaseID']}")
                    if st.button("💾 Save Typed Summary", key=f"save_typed_{case['CaseID']}"):
                        with driver.session() as session:
                            session.run("""
                                MATCH (c:Case {case_id: $case_id})
                                SET c.case_summary = $summary
                            """, {"case_id": case["CaseID"], "summary": typed_summary})
                        st.success("📝 Summary saved to Neo4j.")
                        st.rerun()

                elif mode == "🎤 Dictate with Mic":
                    import whisper
                    import tempfile
                    import os

                    audio = audiorecorder("🎤 Click to Record", "🛑 Stop Recording", key=f"audio_recorder_{case['CaseID']}") # ADDED UNIQUE KEY HERE

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

                            st.success("✅ Transcription complete!")
                            st.text_area("🧾 Transcribed Summary", value=transcription, height=150)

                            with driver.session() as session:
                                session.run("""
                                    MATCH (c:Case {case_id: $case_id})
                                    SET c.case_summary = $summary
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
                                filename = file_url.split("/")[-1]
                                
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Lab Report]({file_url})")
                                
                                if st.button(f"🗑️ Delete", key=f"del_case_lab_{case['CaseID']}_{filename}"):
                                    try:
                                        import requests
                                        delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                                        if delete_res.ok:
                                            with driver.session() as session:
                                                session.run("""
                                                    MATCH (r:UploadedReport {url: $url})
                                                    OPTIONAL MATCH (r)<-[rel]-()
                                                    DELETE rel, r
                                                """, {"url": file_url})
                                            st.success("✅ Lab Report deleted.")
                                            st.rerun()
                                        else:
                                            st.warning("⚠️ Failed to delete from SeaweedFS.")
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
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
                                filename = file_url.split("/")[-1]
                                
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Scan]({file_url})")
                                
                                if st.button(f"🗑️ Delete", key=f"del_case_scan_{case['CaseID']}_{filename}"):
                                    try:
                                        import requests
                                        delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                                        if delete_res.ok:
                                            with driver.session() as session:
                                                session.run("""
                                                    MATCH (r:UploadedReport {url: $url})
                                                    OPTIONAL MATCH (r)<-[rel]-()
                                                    DELETE rel, r
                                                """, {"url": file_url})
                                            st.success("✅ Scan Report deleted.")
                                            st.rerun()
                                        else:
                                            st.warning("⚠️ Failed to delete from SeaweedFS.")
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                                st.markdown("---")
                        else:
                            st.info("No scan reports")
                    
                    # Clinical Insights Column
                    with report_cols[2]:
                        st.markdown("#### 📋 Clinical Insights")
                        if clinical_insights:
                            for report in clinical_insights:
                                file_url = report["url"]
                                uploaded_at = format_datetime(report.get("uploaded_at"))
                                filename = file_url.split("/")[-1]
                                
                                st.markdown(f"🕒 `{uploaded_at}`")
                                st.markdown(f"[📂 View Insight PDF]({file_url})")
                                
                                if st.button(f"🗑️ Delete", key=f"del_case_insight_{case['CaseID']}_{filename}"):
                                    try:
                                        import requests
                                        delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                                        if delete_res.ok:
                                            with driver.session() as session:
                                                session.run("""
                                                    MATCH (r:UploadedReport {url: $url})
                                                    OPTIONAL MATCH (r)<-[rel]-()
                                                    DELETE rel, r
                                                """, {"url": insight["url"]})
                                            st.success("✅ Clinical Insight deleted.")
                                            st.rerun()
                                        else:
                                            st.warning("⚠️ Failed to delete from SeaweedFS.")
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
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
                            summary = record["summary"] if record and record["summary"] else ""

                        # 2. Fetch latest lab & scan reports from UploadedReport nodes
                        with driver.session() as session:
                            result = session.run("""
                                MATCH (c:Case {case_id: $case_id})-[:HAS_REPORT]->(r:UploadedReport)
                                RETURN r.url AS url, r.type AS type, r.uploaded_at AS uploaded_at
                                ORDER BY r.uploaded_at DESC
                            """, {"case_id": case["CaseID"]})
                            reports = result.data()

                        latest_lab = next((r for r in reports if r["type"] == "lab"), None)
                        latest_scan = next((r for r in reports if r["type"] == "scan"), None)

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
                        if latest_scan:
                            try:
                                response = requests.get(latest_scan["url"])
                                if response.ok:
                                    file_content = response.content
                                    # Check for DICOM magic word (DICM)
                                    if file_content[128:132] == b'DICM':
                                        st.warning("DICOM files require specialized handling and cannot be directly displayed as images or processed by the current image encoder.")
                                        scan_image = None # Set to None as it's not a displayable image for current setup
                                    else:
                                        scan_image = encode_image(BytesIO(file_content))
                                else:
                                    st.warning("⚠️ Couldn't fetch the scan image file.")
                            except Exception as e:
                                st.error(f"⚠️ Failed to load scan image: {e}")

                        # 5. Build multimodal prompt & call Gemini
                        prompt = build_multimodal_prompt(summary, lab_data, "Radiology image attached." if scan_image else None)

                        # 6. Run Gemini Agent and Show Result
                        st.markdown("## 🧾 Gemini AI Output")

                        # Call Gemini once and also generate PDF
                        with st.spinner("💬 Generating clinical insight with Gemini..."):
                            gemini_text, pdf_url = call_gemini(prompt, images=[scan_image] if scan_image else [], case_id=case["CaseID"])

                            if not gemini_text or gemini_text.startswith("❌"):
                                st.error(gemini_text)
                            else:
                                # Display all sections
                                sections = gemini_text.split("### ")
                                for idx, section in enumerate(sections):
                                    if not section.strip():
                                        continue

                                    lines = section.strip().splitlines()
                                    title = lines[0].strip(":").strip()
                                    content = "\n".join(lines[1:]).strip()

                                    if title.lower().startswith("soap note"):
                                        st.markdown(f"### 🩺 **{title}**")
                                        st.markdown(content)

                                    elif title.lower().startswith("differential diagnoses"):
                                        st.markdown(f"### 🧠 **{title}**")
                                        st.markdown(content)

                                    elif title.lower().startswith("recommended investigations"):
                                        st.markdown(f"### 🔬 **{title}**")
                                        st.markdown(content)

                                    elif title.lower().startswith("treatment suggestions"):
                                        st.markdown(f"### 💊 **{title}**")
                                        st.markdown(content)

                                    elif title.lower().startswith("file interpretations"):
                                        st.markdown("### 📂 **File Interpretations**")
                                        st.markdown(content)

                                    elif title.lower().startswith("confidence score"):
                                        if content:
                                            st.success(f"✅ Confidence Score: {content}")
                                        else:
                                            next_idx = idx + 1
                                            if next_idx < len(sections):
                                                next_lines = sections[next_idx].strip().splitlines()
                                                next_content = "\n".join(next_lines).strip()
                                                if not next_lines[0].lower().startswith("###"):
                                                    st.success(f"✅ Confidence Score: {next_content}")
                                                else:
                                                    st.info("ℹ️ Confidence score not provided.")
                                            else:
                                                st.info("ℹ️ Confidence score not provided.")
                                    else:
                                        st.markdown(f"### {title}")
                                        st.markdown(content)

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

                        # # 8. Feedback
                        # col1, col2 = st.columns(2)
                        # if col1.button("👍 Good Response", key=f"fb_up_{case['CaseID']}"):
                        #     store_feedback(case["CaseID"], doctor_id, True)
                        #     st.success("Thanks! Feedback noted.")
                        #     st.rerun() # Add rerun to refresh feedback dashboard immediately

                        # if col2.button("👎 Poor Response", key=f"fb_down_{case['CaseID']}"):
                        #     store_feedback(case["CaseID"], doctor_id, False)
                        #     st.warning("Noted. We'll improve.")
                        #     st.rerun() # Add rerun to refresh feedback dashboard immediately


    else:
        st.info("No cases assigned to you yet.")

    if st.button("Logout"):
        del st.session_state.logged_in_doctor
        st.rerun()