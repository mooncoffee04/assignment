from agents.gemini_agent import call_gemini  # <- You already have this

def parse_command(command: str) -> dict:
    """
    Use Gemini to extract intent, patient ID, and case ID from a doctor's query.
    """
    prompt_text = f"""
You are a medical assistant helping extract structured info from doctor queries.

Given this input:  
"{command}"

Return a JSON object with exactly these keys:
- "intent" (must be one of: "get_lab", "get_scan", "get_summary", or null)
- "patient_id" (alphanumeric string or null)
- "case_id" (alphanumeric string or null)

Examples:
- Input: "Show CBC report for patient P123"  
  Output: {{"intent": "get_lab", "patient_id": "P123", "case_id": null}}

- Input: "Chest x-ray for case 89"  
  Output: {{"intent": "get_scan", "patient_id": null, "case_id": "89"}}

ONLY return a JSON object.
"""

    try:
        response = call_gemini(prompt_text)
        import json
        parsed = json.loads(response.strip()) if isinstance(response, str) else response
        return parsed
    except Exception as e:
        return {"intent": None, "patient_id": None, "case_id": None, "error": str(e)}
