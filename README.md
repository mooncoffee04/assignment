# 🏥 Multimodal Clinical Insight Assistant – Setup Guide

This project is a Streamlit-based app designed to help doctors interact with patient data using natural language, voice commands, and multimodal inputs like lab/scan reports.

---

## 🔧 Prerequisites

1. **Python**: Version 3.10 or above
2. **Neo4j**: Installed or use [Neo4j Aura](https://neo4j.com/cloud/aura/)
3. **Docker**: For SeaweedFS setup (or skip if not using blob storage)
4. **Git** (optional but recommended)
5. **Whisper Model**: Used for speech-to-text via OpenAI's Whisper

---

## 📁 Folder Structure

```
ASSIGNMENT/
│
├── app.py                       # Streamlit entry point
├── home.py                      # Main app logic
├── agents/                      # AI + Gemini agent logic
├── pages/                       # Streamlit multipage support
├── utils/, whisper/, ...        # Helper modules
├── seaweedfs-docker/            # Docker config for SeaweedFS
├── .env                         # Add your API keys here
├── feedback_store.jsonl         # Stores AI feedback logs
├── sample_patient.csv           # Sample patients for Neo4j
└── output_clean.wav             # Example audio file

```
# 1. Clone & Set Up Environment
```
git clone <your-repo-url>
cd ASSIGNMENT
```

# Create virtual environment (Terminal)
```
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
```

# Install dependencies
```
pip install -r requirements.txt
```

# 2. Create a ```.env``` file
```
GEMINI_API_KEY=your_gemini_api_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
```

# 3. Run SeaWeedFS via Docker (Terminal)
```
cd seaweedfs-docker
docker-compose up -d
```

# 4. Setup Whisper for Speech-to-text
```
pip install openai-whisper
```

# 5. Run the App
```
streamlit run home.py
```

# 6. Sample Data for Neo4j
Use the provided ```sample_patient.csv``` and ```sample_doctor.csv``` with:
```
python neo4jpatients.py
python neo4jdoctors.py
```

# 7. Supported Features

- Ask via Command (Typed or Dictated) — powered by Gemini + Whisper

- Auto-generated SOAP notes from lab/scan reports

- Patient/case dashboard with uploaded audio/image reports

- Feedback tracking and storage

- PDF generation + SeaweedFS file handling
