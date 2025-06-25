import json
import traceback
from agents.gemini_agent import call_gemini # Ensure this import is present

def process_natural_language_command(command: str, driver):
    """
    Processes a natural language command to extract intent and entities,
    then generates and executes a Neo4j Cypher query.

    Args:
        command (str): The natural language command from the user.
        driver: Neo4j database driver.

    Returns:
        dict: A dictionary containing success status, query, data, or error message.
    """
    
    # Step 1: Use Gemini to parse the command and extract intent and entities
    # The prompt instructs Gemini to return a JSON object with intent and entities.
    parsing_prompt = f"""
    You are an AI assistant designed to extract information from clinical commands.
    Analyze the following command and extract its intent and any relevant entities.
    
    Expected JSON output format:
    ```json
    {{
        "intent": "show_report" | "list_patients" | "summarize_case" | "unknown",
        "case_id": "CXXX" (if present, e.g., "C010"),
        "report_type": "lab" | "scan" | "prescription" | "x-ray" | "ct scan" | "mri" (if present and specifically mentioned),
        "patient_name": "John Doe" (if present),
        "error": "Reason for unknown intent or missing entity" (if intent is unknown or entity missing for required intent)
    }}
    ```

    Command: "{command}"
    """
    
    try:
        # Assuming call_gemini returns only the text response (JSON string)
        # when called with only a prompt for parsing.
        gemini_result = call_gemini(parsing_prompt)
        gemini_response_text = gemini_result["text"] if isinstance(gemini_result, dict) else gemini_result
 

        # Ensure response is not empty or None and is a string
        # print("⚠️ Gemini returned:", repr(gemini_response_text))
        if not gemini_response_text or not isinstance(gemini_response_text, str):
            return {"success": False, "error": "AI did not return a valid text response for parsing the command.", "suggestion": "There might be an issue with the AI service or its configuration. Please check your Gemini API key and network connection."}

        # NEW LOGIC: Strip Markdown code block delimiters
        # This handles cases where the AI wraps the JSON in ```json...``` or just ```...```
        if gemini_response_text.startswith("```json\n") and gemini_response_text.endswith("\n```"):
            gemini_response_text = gemini_response_text[len("```json\n"):-len("\n```")]
        elif gemini_response_text.startswith("```\n") and gemini_response_text.endswith("\n```"):
            gemini_response_text = gemini_response_text[len("```\n"):-len("\n```")]
        
        # Strip any leading/trailing whitespace that might remain
        gemini_response_text = gemini_response_text.strip()

        command_parsed = json.loads(gemini_response_text)
    except json.JSONDecodeError as e:
        # Include the raw response in the error message for debugging
        return {"success": False, "error": f"AI response was not valid JSON: {e}. Raw response: '{gemini_response_text}'", "suggestion": "Please try rephrasing your command more clearly. Ensure it's concise and specific."}
    except Exception as e:
        print("=== ERROR while calling Gemini ===")
        traceback.print_exc()  # This prints the full stack trace to the terminal
        return {
            "success": False,
            "error": f"An unexpected error occurred while parsing command with AI: {e}",
            "suggestion": "Ensure the command is clear and simple."
    }

    intent = command_parsed.get("intent")
    case_id = command_parsed.get("case_id")
    report_type = command_parsed.get("report_type")
    patient_name = command_parsed.get("patient_name")

    if intent == "show_report":
        if not case_id and not patient_name:
            return {"success": False, "error": "Missing case ID or patient name for 'show report' command.", "suggestion": "Please specify a case ID (e.g., 'C010') or patient name (e.g., 'for John Doe')."}
        if not report_type:
            return {"success": False, "error": "Missing report type for 'show report' command.", "suggestion": "Please specify a report type (e.g., 'lab report', 'chest X-ray')."}
        
        query_parts = ["MATCH (p:Patient)<-[:BELONGS_TO]-(c:Case)-[:HAS_REPORT]->(r:UploadedReport)"]
        where_clauses = []
        params = {}

        if case_id:
            where_clauses.append("c.case_id = $case_id")
            params["case_id"] = case_id
        if patient_name:
            # Use CONTAINS for flexible patient name matching
            where_clauses.append("p.name CONTAINS $patient_name")
            params["patient_name"] = patient_name
        
        if report_type:
            # Map common user-friendly report types to the types stored in your database
            type_map = {
                "lab": "lab", "lab report": "lab",
                "scan": "scan", "x-ray": "scan", "chest x-ray": "scan", "mri": "scan", "ct scan": "scan",
                "prescription": "prescription", "insight": "prescription", "clinical insight": "prescription"
            }
            mapped_type = type_map.get(report_type.lower())
            if mapped_type:
                where_clauses.append("r.type = $report_type")
                params["report_type"] = mapped_type
            else:
                return {"success": False, "error": f"Unsupported report type: '{report_type}'.", "suggestion": "Supported types are 'lab', 'scan', 'prescription', 'x-ray', 'mri', 'ct scan'."}

        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))
        
        query_parts.append("RETURN r.url AS url, r.type AS type, r.uploaded_at AS uploaded_at ORDER BY r.uploaded_at DESC")
        cypher_query = "\n".join(query_parts)

        with driver.session() as session:
            result = session.run(cypher_query, params)
            data = result.data()
            return {"success": True, "query": cypher_query, "data": data if data else []}

    elif intent == "list_patients":
        cypher_query = "MATCH (p:Patient) RETURN p.id AS id, p.name AS name"
        with driver.session() as session:
            result = session.run(cypher_query)
            data = result.data()
            return {"success": True, "query": cypher_query, "data": data if data else []}

    elif intent == "summarize_case":
        if not case_id:
            return {"success": False, "error": "Missing case ID for 'summarize case' command.", "suggestion": "Please specify a case ID (e.g., 'C010')."}
        
        cypher_query = "MATCH (c:Case {case_id: $case_id}) RETURN c.case_summary AS summary"
        with driver.session() as session:
            result = session.run(cypher_query, {"case_id": case_id})
            summary_data = result.single()
            if summary_data and summary_data["summary"]:
                return {"success": True, "query": cypher_query, "data": {"summary": summary_data["summary"]}}
            else:
                return {"success": True, "query": cypher_query, "data": None, "error": "No summary found for this case.", "suggestion": "You might need to add a summary for this case."}
    
    elif intent == "unknown":
        error_msg = command_parsed.get("error", "Could not understand your command.")
        return {"success": False, "error": error_msg, "suggestion": "Please try rephrasing your command. For example: 'Show lab report for case C010' or 'List all patients'."}

    else:
        return {"success": False, "error": "Unsupported command intent.", "suggestion": "Please try commands like 'Show [report type] for [case ID]', 'List all patients', or 'Summarize case [case ID]'."}