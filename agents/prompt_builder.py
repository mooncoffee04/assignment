def build_multimodal_prompt(case_summary, lab_data=None, scan_description=None):
    prompt = f"""
You are a clinical AI assistant. Given the following data, generate a structured SOAP note, differential diagnoses, investigations, treatments, file interpretations, and a confidence score.
Also make sure that the note generated is HIPAA and GDPR compliant, you're not allowed to disclose patient's PII. It is mandatory for you to respond with a confidence score.

## Subjective (From Doctor Summary)
{case_summary}

"""

    if lab_data:
        prompt += f"\n## Lab Report Findings:\n{lab_data}\n"

    if scan_description:
        prompt += f"\n## Radiology Image Analysis:\n{scan_description}\n"

    prompt += """
Respond in the following format:

### SOAP Note:
- Subjective:
- Objective:
- Assessment:
- Plan:

### Differential Diagnoses:
1. 
2. 

### Recommended Investigations:
- 

### Treatment Suggestions:
- 

### File Interpretations:
- Lab Report: 
- Scan: 

### Confidence Score (0–1):
"""

    return prompt.strip()
