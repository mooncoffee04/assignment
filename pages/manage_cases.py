import streamlit as st
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, date
from dateutil import parser
import pytz # Ensure pytz is imported at the top level
import requests # Needed for SeaweedFS deletion


# --------- Date-Time Parser (Copy from app.py) --------------------
def format_datetime(datetime_value):
    """
    Centralized datetime formatting function
    Handles various datetime formats and returns a consistent display format
    """
    if not datetime_value:
        return "Unknown"
    
    try:
        # Ensure datetime is imported from its module directly if needed here
        # import pytz and parser are already at top of this script
        
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


# -------- Load env and connect to Neo4j (Copy from app.py) --------
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# -------- Utility Functions for Case Management --------
# --- Handle form clearing flag ---
if st.session_state.get("clear_form_fields_flag", False):
    keys_to_clear = [
        "new_patient_type",
        "new_patient_id_input_add_case",
        "new_patient_name_input_add_case",
        "new_case_id_input_add_case_existing",
        "new_case_id_input_add_case_new",
        "new_case_summary_input_add_case_existing",
        "new_case_summary_input_add_case_new",
        "selected_patient_add_case"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state["clear_form_fields_flag"] = False  # Reset the flag

def clear_new_case_inputs():
    """
    Safely clears session state values by using a rerun flag mechanism.
    """
    st.session_state["clear_form_fields_flag"] = True
    st.rerun()

    
def _get_next_case_id(driver):
    """
    Generates the next available case ID based on existing case IDs (e.g., C001, C002, ...)
    without using APOC.
    """
    with driver.session() as session:
        # Fetch all case_ids that start with 'C'
        result = session.run("""
            MATCH (c:Case)
            WHERE c.case_id STARTS WITH 'C'
            RETURN c.case_id AS case_id
        """)
        
        max_num = 0
        for record in result:
            case_id_str = record["case_id"]
            try:
                # Attempt to extract numeric part after 'C' and convert to int
                num_part = int(case_id_str[1:])
                max_num = max(max_num, num_part)
            except ValueError:
                # Ignore case_ids that do not follow the C### numeric format
                continue # Skip invalid IDs and continue processing
        
        next_num = max_num + 1
        return f"C{next_num:03d}" # Format as C001, C010, C123


def _get_next_patient_id(driver):
    """
    Generates the next available patient ID based on existing patient IDs (e.g., P001, P002, ...)
    without using APOC.
    """
    with driver.session() as session:
        # Fetch all patient_ids that start with 'P'
        result = session.run("""
            MATCH (p:Patient)
            WHERE p.id STARTS WITH 'P'
            RETURN p.id AS patient_id
        """)
        
        max_num = 0
        for record in result:
            patient_id_str = record["patient_id"]
            try:
                # Attempt to extract numeric part after 'P' and convert to int
                num_part = int(patient_id_str[1:])
                max_num = max(max_num, num_part)
            except ValueError:
                # Ignore patient_ids that do not follow the P### numeric format
                continue # Skip invalid IDs and continue processing
        
        next_num = max_num + 1
        return f"P{next_num:03d}" # Format as P001, P010, P123


def fetch_patient_name_by_id(driver, patient_id):
    """Fetches patient name given patient ID."""
    with driver.session() as session:
        result = session.run("MATCH (p:Patient {id: $patient_id}) RETURN p.name AS name", {"patient_id": patient_id})
        record = result.single()
        return record["name"] if record else None


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
    Deletes a case and its associated reports and feedback from Neo4j.
    Does NOT delete the patient.
    """
    try:
        with driver.session() as session:
            # Query to find related report URLs to delete from SeaweedFS
            report_urls_result = session.run(
                """
                MATCH (c:Case {case_id: $case_id})-[r_rel:HAS_REPORT]->(ur:UploadedReport)
                RETURN ur.url AS url
                """, {"case_id": case_id}
            ).data()

            # Delete files from SeaweedFS if they exist
            if report_urls_result:
                for record in report_urls_result:
                    file_url = record["url"]
                    if file_url: # Ensure URL is not empty
                        filename = file_url.split("/")[-1]
                        try:
                            # Note: Ensure your SeaweedFS access is correctly configured (e.g., firewall)
                            delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                            if delete_res.ok:
                                st.info(f"🗑️ Deleted file from SeaweedFS: {filename}")
                            else:
                                st.warning(f"⚠️ Failed to delete file {filename} from SeaweedFS (Status: {delete_res.status_code}).")
                        except Exception as e:
                            st.error(f"❌ Error deleting file {filename} from SeaweedFS: {e}")

            # Delete the case, its uploaded reports, and feedback nodes
            session.run(
                """
                MATCH (c:Case {case_id: $case_id})
                OPTIONAL MATCH (c)-[:HAS_REPORT]->(ur:UploadedReport)
                OPTIONAL MATCH (c)-[:HAS_FEEDBACK]->(f:Feedback)
                DETACH DELETE c, ur, f
                """,
                {"case_id": case_id}
            )

        return True, f"✅ Case '{case_id}' and its associated data deleted successfully!"
    except Exception as e:
        return False, f"❌ An error occurred while deleting case '{case_id}': {e}"


def delete_patient_from_neo4j(driver, patient_id):
    """
    Deletes a patient and ALL their associated cases, reports, and feedback from Neo4j.
    Also deletes files from SeaweedFS.
    """
    try:
        with driver.session() as session:
            # First, get all report URLs associated with this patient's cases
            report_urls_result = session.run(
                """
                MATCH (p:Patient {id: $patient_id})<-[:BELONGS_TO]-(c:Case)-[:HAS_REPORT]->(ur:UploadedReport)
                RETURN ur.url AS url
                """, {"patient_id": patient_id}
            ).data()

            # Delete files from SeaweedFS if they exist
            if report_urls_result:
                for record in report_urls_result:
                    file_url = record["url"]
                    if file_url: # Ensure URL is not empty
                        filename = file_url.split("/")[-1]
                        try:
                            delete_res = requests.delete(f"http://localhost:8888/seaweedfs/{filename}")
                            if delete_res.ok:
                                st.info(f"🗑️ Deleted file from SeaweedFS: {filename}")
                            else:
                                st.warning(f"⚠️ Failed to delete file {filename} from SeaweedFS (Status: {delete_res.status_code}).")
                        except Exception as e:
                            st.error(f"❌ Error deleting file {filename} from SeaweedFS: {e}")

            # Get count of cases that will be deleted
            case_count_result = session.run(
                """
                MATCH (p:Patient {id: $patient_id})<-[:BELONGS_TO]-(c:Case)
                RETURN count(c) AS case_count
                """, {"patient_id": patient_id}
            ).single()
            
            case_count = case_count_result["case_count"] if case_count_result else 0

            # Delete the patient and all associated cases, reports, and feedback
            session.run(
                """
                MATCH (p:Patient {id: $patient_id})
                OPTIONAL MATCH (p)<-[:BELONGS_TO]-(c:Case)
                OPTIONAL MATCH (c)-[:HAS_REPORT]->(ur:UploadedReport)
                OPTIONAL MATCH (c)-[:HAS_FEEDBACK]->(f:Feedback)
                DETACH DELETE p, c, ur, f
                """,
                {"patient_id": patient_id}
            )

        return True, f"✅ Patient '{patient_id}' and all {case_count} associated cases deleted successfully!"
    except Exception as e:
        return False, f"❌ An error occurred while deleting patient '{patient_id}': {e}"


def fetch_all_patients_with_cases():
    """
    Fetches all patients assigned to the logged-in doctor with their case information.
    """
    # Ensure doctor_id is available in session state
    if "logged_in_doctor" not in st.session_state or not st.session_state.logged_in_doctor:
        return []

    doctor_id = st.session_state.logged_in_doctor

    with driver.session() as session:
        result = session.run("""
            MATCH (d:Doctor {id: $doctor_id})-[:HANDLES]->(c:Case)-[:BELONGS_TO]->(p:Patient)
            WHERE p.id IS NOT NULL AND p.name IS NOT NULL AND trim(p.name) <> ''
            RETURN p.id AS patient_id, 
                   p.name AS patient_name,
                   collect(DISTINCT {case_id: c.case_id, summary: c.case_summary, created_at: c.created_at}) AS cases
            ORDER BY p.name
        """, {"doctor_id": doctor_id})
        
        patients_data = []
        for record in result:
            # Additional safety check in Python
            patient_id = record["patient_id"]
            patient_name = record["patient_name"]
            
            if patient_id and patient_name and patient_name.strip():
                patient_data = {
                    "id": patient_id,
                    "name": patient_name.strip(),
                    "cases": record["cases"]
                }
                patients_data.append(patient_data)
        
        return patients_data


def fetch_all_patients():
    """
    Fetches all patient IDs and names assigned to the logged-in doctor.
    """
    # Ensure doctor_id is available in session state
    if "logged_in_doctor" not in st.session_state or not st.session_state.logged_in_doctor:
        return []

    doctor_id = st.session_state.logged_in_doctor

    with driver.session() as session:
        result = session.run("""
            MATCH (d:Doctor {id: $doctor_id})-[:HANDLES]->(c:Case)-[:BELONGS_TO]->(p:Patient)
            WHERE p.id IS NOT NULL AND p.name IS NOT NULL AND trim(p.name) <> ''
            RETURN DISTINCT p.id AS id, p.name AS name
            ORDER BY p.name
        """, {"doctor_id": doctor_id})
        
        patients = []
        for r in result:
            patient_id = r["id"]
            patient_name = r["name"]
            
            # Additional safety check
            if patient_id and patient_name and patient_name.strip():
                patients.append({"id": patient_id, "name": patient_name.strip()})
        
        return patients

def fetch_cases_for_doctor(doctor_id): # Copied from app.py
    """
    Fetches all cases assigned to a specific doctor.
    This ensures that only cases the logged-in doctor handles are displayed.
    """
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

# -------- Streamlit Page UI --------
st.set_page_config(page_title="Manage Cases", page_icon="⚙️", layout="wide")
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
.stTextArea > label {
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

st.sidebar.title("Navigation")
st.sidebar.page_link("home.py", label="🏠 Home")

st.markdown("# ⚙️ Manage Cases")

# Ensure doctor is logged in
if "logged_in_doctor" not in st.session_state:
    st.warning("Please log in to access this page.")
    st.stop() # Stop execution if not logged in

doctor_id = st.session_state.logged_in_doctor

st.info(f"You are managing cases for Doctor: **{doctor_id}**")


# --- Add New Case Section ---
st.markdown("---")
st.markdown("## ➕ Add New Case")

add_case_tabs = st.tabs(["Add for Existing Patient", "Add for New Patient"])

# Initialize session state for text inputs if not present (important for clearing)
# These keys are explicitly for this page to prevent conflicts
if "selected_patient_add_case" not in st.session_state:
    st.session_state["selected_patient_add_case"] = ""
if "new_patient_id_input_add_case" not in st.session_state:
    st.session_state["new_patient_id_input_add_case"] = ""
if "new_patient_name_input_add_case" not in st.session_state:
    st.session_state["new_patient_name_input_add_case"] = ""
if "new_case_summary_input_add_case_existing" not in st.session_state:
    st.session_state["new_case_summary_input_add_case_existing"] = ""
if "new_case_summary_input_add_case_new" not in st.session_state:
    st.session_state["new_case_summary_input_add_case_new"] = ""

with add_case_tabs[0]: # Add for Existing Patient
    st.markdown("### For an Existing Patient")
    
    # Fetch patients with their cases
    patients_with_cases = fetch_all_patients_with_cases()
    
    if not patients_with_cases:
        st.info("No existing patients found. Please add a new patient first.")
    else:
        # Create patient selection options
        patient_options = {f"{p['name']} ({p['id']})": p for p in patients_with_cases}

        selected_patient_display = st.selectbox(
            "Select an Existing Patient",
            options=[""] + sorted(list(patient_options.keys())), # Add empty option and sort for readability
            key="selected_patient_add_case"
        )
        
        patient_data = None
        if selected_patient_display:
            patient_data = patient_options[selected_patient_display]
            
            # Display patient information and existing cases
            st.info(f"**Patient ID:** {patient_data['id']}")
            st.info(f"**Patient Name:** {patient_data['name']}")
            
            # Show existing cases for this patient
            if patient_data['cases']:
                st.markdown("**Existing Cases for this Patient:**")
                for case in patient_data['cases']:
                    created_at_formatted = format_datetime(case['created_at'])
                    st.markdown(f"- **{case['case_id']}**: {case['summary'][:100]}{'...' if len(case['summary']) > 100 else ''} *(Created: {created_at_formatted})*")
            else:
                st.markdown("*No existing cases found for this patient.*")

        # Auto-generate Case ID
        auto_generated_case_id = _get_next_case_id(driver)
        st.text_input("New Case ID (Auto-generated)", value=auto_generated_case_id, disabled=True, key="auto_case_id_existing")
        
        new_case_summary_existing = st.text_area("Case Summary", height=100, key="new_case_summary_input_add_case_existing",
                                                  value=st.session_state.get("new_case_summary_input_add_case_existing", ""))

        if st.button("Create Case for Existing Patient", key="submit_existing_patient_case_btn"):
            if not patient_data or not new_case_summary_existing.strip():
                st.warning("⚠️ Please select a patient and provide a case summary.")
            else:
                success, message = add_new_case_to_neo4j(
                    driver,
                    patient_data['id'],
                    patient_data['name'], 
                    auto_generated_case_id,
                    new_case_summary_existing.strip(),
                    doctor_id
                )
                if success:
                    st.success(message)
                    clear_new_case_inputs() # Clear form fields
                    st.rerun() # Refresh page
                else:
                    st.error(message)

with add_case_tabs[1]: # Add for New Patient
    st.markdown("### For a New Patient")

    # Auto-generate Patient ID
    auto_generated_patient_id = _get_next_patient_id(driver)
    st.text_input("New Patient ID (Auto-generated)", value=auto_generated_patient_id, disabled=True, key="auto_patient_id_new")
    
    new_patient_name = st.text_input("New Patient Name (e.g., John Doe)", key="new_patient_name_input_add_case",
                                     value=st.session_state.get("new_patient_name_input_add_case", ""))
    
    # Auto-generate Case ID
    auto_generated_case_id_new = _get_next_case_id(driver)
    st.text_input("New Case ID (Auto-generated)", value=auto_generated_case_id_new, disabled=True, key="auto_case_id_new")
    
    new_case_summary_new = st.text_area("Case Summary", height=100, key="new_case_summary_input_add_case_new",
                                        value=st.session_state.get("new_case_summary_input_add_case_new", ""))

    if st.button("Create Case for New Patient", key="submit_new_patient_case_btn"):
        if not all([new_patient_name.strip(), new_case_summary_new.strip()]):
            st.warning("⚠️ Please fill in the patient name and case summary.")
        else:
            success, message = add_new_case_to_neo4j(
                driver,
                auto_generated_patient_id,
                new_patient_name.strip(),
                auto_generated_case_id_new,
                new_case_summary_new.strip(),
                doctor_id
            )
            if success:
                st.success(message)
                clear_new_case_inputs() # Clear form fields
                st.rerun() # Refresh page
            else:
                st.error(message)

st.markdown("---")


# --- Delete Section ---
st.markdown("## 🗑️ Delete Cases or Patients")
st.warning("🚨 Deletion is irreversible and will remove all associated data from the database and storage (SeaweedFS).")
st.info("Showing only cases and patients assigned to you for deletion.")

delete_tabs = st.tabs(["Delete Individual Cases", "Delete Entire Patients"])

with delete_tabs[0]: # Delete Cases
    st.markdown("### Delete Individual Cases")
    st.info("This will delete only the selected case, keeping the patient and their other cases intact.")
    
    # Fetch cases *only* for the logged-in doctor
    cases_to_delete = fetch_cases_for_doctor(doctor_id) 

    if cases_to_delete:
        df_cases_to_delete = pd.DataFrame(cases_to_delete)
        df_cases_to_delete['CreatedAt'] = df_cases_to_delete['CreatedAt'].apply(format_datetime)

        # Display cases with delete buttons
        for index, row in df_cases_to_delete.iterrows():
            case_id = row['CaseID']
            patient_id = row['PatientID']
            patient_name = row['PatientName']
            summary = row['Summary']
            created_at = row['CreatedAt']

            st.markdown(f"**Case ID:** {case_id}")
            st.markdown(f"**Patient:** {patient_name} (`{patient_id}`)")
            st.markdown(f"**Summary:** {summary}")
            st.markdown(f"**Created At:** {created_at}")
            
            # Use session state to manage confirmation for each specific case
            confirm_state_key = f'confirm_delete_case_{case_id}'
            
            # Initial delete button
            if st.session_state.get(confirm_state_key) is not True: # Only show initial delete button if not in confirmation state
                if st.button("🗑️ Delete This Case", key=f"delete_case_btn_{case_id}"):
                    st.session_state[confirm_state_key] = True # Set state to show confirmation
                    st.rerun() # Rerun to display confirmation buttons

            # Confirmation buttons
            if st.session_state.get(confirm_state_key) is True:
                st.warning(f"Are you absolutely sure you want to delete Case '{case_id}'? This action cannot be undone and related files will be removed from storage.")
                col_confirm, col_cancel = st.columns(2)
                
                with col_confirm:
                    if st.button(f"**Confirm Delete Case '{case_id}'**", key=f"confirm_delete_case_action_{case_id}"):
                        success, message = delete_case_from_neo4j(driver, case_id)
                        if success:
                            st.success(message)
                            del st.session_state[confirm_state_key] # Clear confirmation state
                            st.rerun() # Refresh page
                        else:
                            st.error(message)
                with col_cancel:
                    if st.button("Cancel", key=f"cancel_delete_case_action_{case_id}"):
                        st.info("Case deletion cancelled.")
                        del st.session_state[confirm_state_key] # Clear confirmation state
                        st.rerun() # Refresh page
            
            st.markdown("---") # Separator between cases
    else:
        st.info("No cases found that are assigned to you for deletion.")

with delete_tabs[1]: # Delete Patients
    st.markdown("### Delete Entire Patients")
    st.error("⚠️ **WARNING**: This will delete the patient AND ALL their cases, reports, and feedback permanently!")
    
    # Fetch patients with their cases
    patients_with_cases = fetch_all_patients_with_cases()
    
    if patients_with_cases:
        # Display patients with their cases and delete buttons
        for patient in patients_with_cases:
            patient_id = patient['id']
            patient_name = patient['name']
            cases = patient['cases']
            
            st.markdown(f"**Patient ID:** {patient_id}")
            st.markdown(f"**Patient Name:** {patient_name}")
            st.markdown(f"**Number of Cases:** {len(cases)}")
            
            # Show all cases for this patient
            if cases:
                st.markdown("**Cases that will be deleted:**")
                for case in cases:
                    created_at_formatted = format_datetime(case['created_at'])
                    st.markdown(f"- **{case['case_id']}**: {case['summary'][:100]}{'...' if len(case['summary']) > 100 else ''} *(Created: {created_at_formatted})*")
            
            # Use session state to manage confirmation for each specific patient
            confirm_state_key = f'confirm_delete_patient_{patient_id}'
            
            # Initial delete button
            if st.session_state.get(confirm_state_key) is not True:
                if st.button(f"🗑️ Delete Patient '{patient_name}'", key=f"delete_patient_btn_{patient_id}"):
                    st.session_state[confirm_state_key] = True
                    st.rerun()

            # Confirmation buttons
            if st.session_state.get(confirm_state_key) is True:
                st.error(f"⚠️ **FINAL WARNING**: You are about to delete Patient '{patient_name}' ({patient_id}) and ALL {len(cases)} associated cases. This action cannot be undone!")
                col_confirm, col_cancel = st.columns(2)
                
                with col_confirm:
                    if st.button(f"**CONFIRM DELETE PATIENT '{patient_name}'**", key=f"confirm_delete_patient_action_{patient_id}"):
                        success, message = delete_patient_from_neo4j(driver, patient_id)
                        if success:
                            st.success(message)
                            del st.session_state[confirm_state_key]
                            st.rerun()
                        else:
                            st.error(message)
                with col_cancel:
                    if st.button("Cancel", key=f"cancel_delete_patient_action_{patient_id}"):
                        st.info("Patient deletion cancelled.")
                        del st.session_state[confirm_state_key]
                        st.rerun()
            
            st.markdown("---") # Separator between patients
    else:
        st.info("No patients found that are assigned to you for deletion.")