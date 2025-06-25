import os
import json
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

import google.generativeai as genai
from agents.pdf_exporter import generate_pdf_and_save

# === Configuration ===
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")
FEEDBACK_FILE = "feedback_store.jsonl"


# === MAIN FUNCTION ===
def call_gemini(prompt_text, images=None, case_id=None, doctor_id=None):
    """
    Call Gemini API and optionally generate PDF and return feedback.
    Handles empty responses or safety blocks from Gemini.
    """
    parts = [{"text": prompt_text}]
    if images:
        parts.extend(images)

    gemini_text = "❌ Gemini returned no output." # Default error message
    pdf_url = None
    feedback = None

    try:
        response = model.generate_content(parts)

        # === Robust Response Parsing ===
        if response.text: # Simplest case: direct text attribute
            gemini_text = response.text
        elif response.candidates: # Check if there are any candidates
            # Ensure candidates list is not empty before accessing index 0
            if response.candidates[0].content and response.candidates[0].content.parts:
                # Check if the parts list is not empty and has text
                if response.candidates[0].content.parts[0].text:
                    gemini_text = response.candidates[0].content.parts[0].text
                else:
                    gemini_text = "❌ Gemini returned empty content part."
            else:
                gemini_text = "❌ Gemini candidate has no content or parts."
        else:
            gemini_text = "❌ Gemini returned no candidates."

        # Log safety feedback if any, regardless of whether text was generated
        if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
            # You might want more detailed logging for safety_ratings
            logger.warning(f"Gemini prompt_feedback: {response.prompt_feedback}")
            if response.prompt_feedback.safety_ratings:
                gemini_text += f" (Safety reasons: {response.prompt_feedback.safety_ratings})"


        pdf_url = None
        if case_id and gemini_text and not gemini_text.startswith("❌"):
            try:
                pdf_url = generate_pdf_and_save(case_id, gemini_text)
            except Exception as pdf_error:
                print(f"PDF generation failed: {pdf_error}")

        feedback = get_feedback_from_file(case_id, doctor_id) if case_id and doctor_id else None

        return {
            "text": gemini_text,
            "pdf_url": pdf_url,
            "feedback": feedback
        }

    except Exception as e:
        return {
            "text": f"❌ Gemini API Error: {str(e)}",
            "pdf_url": None,
            "feedback": None
        }


# === FEEDBACK STORE ===
def store_feedback_to_file(case_id, doctor_id, is_good):
    entry = {
        "case_id": case_id,
        "doctor_id": doctor_id,
        "is_good": is_good,
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception as e:
        print(f"Error writing feedback: {e}")
        return False


def get_feedback_from_file(case_id, doctor_id):
    try:
        with open(FEEDBACK_FILE, "r") as f:
            for line in f:
                entry = json.loads(line)
                if entry["case_id"] == case_id and entry["doctor_id"] == doctor_id:
                    return {
                        "is_good": entry["is_good"],
                        "timestamp": entry["timestamp"]
                    }
    except FileNotFoundError:
        return None
    return None


# === OPTIONAL: Send feedback to Gemini (Learning loop) ===
def send_feedback_to_gemini(feedback_prompt, is_positive=True):
    try:
        system_prompt = (
            "You are a medical AI learning system. You receive feedback from qualified doctors "
            "about clinical responses. Your job is to acknowledge the feedback and confirm it will "
            "be used to improve future results."
        )
        full_prompt = f"{system_prompt}\n\n{feedback_prompt}"

        response = model.generate_content(full_prompt)
        response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text

        logger.info(f"[GEMINI FEEDBACK - {'POSITIVE' if is_positive else 'NEGATIVE'}] {response_text[:100]}...")
        return response_text

    except Exception as e:
        logger.error(f"Error sending feedback to Gemini: {str(e)}")
        return f"Feedback logged locally due to error: {str(e)}"
