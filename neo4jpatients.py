import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

CSV_FILE = "sample_patient.csv"

def upload_cases_to_neo4j(csv_file):
    df = pd.read_csv(csv_file)
    df.fillna("", inplace=True)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    with driver.session() as session:
        for _, row in df.iterrows():
            session.run(
                """
                MERGE (d:Doctor {id: $doctor_id})

                MERGE (p:Patient {id: $patient_id})
                ON CREATE SET p.name = $patient_name

                MERGE (c:Case {case_id: $case_id})
                SET c.case_summary = $case_summary,
                    c.created_at = datetime()

                MERGE (d)-[:HANDLES]->(c)
                MERGE (c)-[:BELONGS_TO]->(p)

                WITH c, p, $lab_report_link AS lab_url, $scan_link AS scan_url

                FOREACH (_ IN CASE WHEN lab_url <> "" THEN [1] ELSE [] END |
                    CREATE (r1:Report {url: lab_url, type: "lab", uploaded_at: datetime()})
                    MERGE (c)-[:HAS_REPORT]->(r1)
                    CREATE (ur1:UploadedReport {url: lab_url, type: "lab", uploaded_at: datetime()})
                    MERGE (p)-[:HAS_UPLOADED]->(ur1)
                )

                FOREACH (_ IN CASE WHEN scan_url <> "" THEN [1] ELSE [] END |
                    CREATE (r2:Report {url: scan_url, type: "scan", uploaded_at: datetime()})
                    MERGE (c)-[:HAS_REPORT]->(r2)
                    CREATE (ur2:UploadedReport {url: scan_url, type: "scan", uploaded_at: datetime()})
                    MERGE (p)-[:HAS_UPLOADED]->(ur2)
                )
                """,
                {
                    "case_id": row["case_id"],
                    "patient_id": row["patient_id"],
                    "patient_name": row["patient_name"],
                    "doctor_id": row["doctor_id"],
                    "lab_report_link": row["lab_report_link"],
                    "scan_link": row["scan_link"],
                    "case_summary": row["case_summary"]
                }
            )

    driver.close()
    print("✅ All cases and uploaded reports saved to Neo4j.")

if __name__ == "__main__":
    upload_cases_to_neo4j(CSV_FILE)
