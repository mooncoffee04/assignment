import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Neo4j connection
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Read doctors.csv
df = pd.read_csv("sample_doctor.csv")

# Define Cypher upload logic
def upload_doctors(tx, doctor_id, name, role):
    tx.run(
        """
        MERGE (d:Doctor {id: $doctor_id})
        SET d.name = $name,
            d.role = $role
        """,
        doctor_id=doctor_id,
        name=name,
        role=role,
    )

# Write to Neo4j
with driver.session() as session:
    for _, row in df.iterrows():
        session.execute_write(upload_doctors, row['doctor_id'], row['doctor_name'], row['role'])

print("✅ Doctors uploaded successfully.")