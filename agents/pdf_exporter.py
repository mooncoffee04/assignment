import requests
import datetime
import os
import tempfile
from fpdf import FPDF
import re

def generate_pdf_and_save(case_id, gemini_text):
    """
    Generate PDF from Gemini text and upload to SeaweedFS

    Args:
        case_id: Case ID for filename
        gemini_text: The text content from Gemini

    Returns:
        str: URL of uploaded PDF or None if failed
    """
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{case_id}_clinical_insight_{timestamp}.pdf"

        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)

        # Add title
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Clinical Insight Report - Case {case_id}", ln=True, align="C")
        pdf.ln(5)

        # Add timestamp
        pdf.set_font("Arial", "I", 8)
        pdf.cell(0, 10, f"Generated on: {datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')}", ln=True)
        pdf.ln(5)

        # Process the text content
        pdf.set_font("Arial", size=10)

        # Split content into sections
        sections = gemini_text.split("### ")

        for section in sections:
            if not section.strip():
                continue

            lines = section.strip().splitlines()
            if not lines:
                continue

            # First line is the title
            title = lines[0].strip(":").strip()
            content = "\n".join(lines[1:]).strip()

            # Add section title
            if title:
                pdf.set_font("Arial", "B", 12)
                pdf.ln(3)
                # Clean title for PDF
                clean_title = re.sub(r'[^\w\s-]', '', title)
                pdf.cell(0, 8, clean_title, ln=True)
                pdf.ln(2)

            # Add section content
            pdf.set_font("Arial", size=10)
            if content:
                # --- START MODIFICATION ---
                # Remove common Markdown elements
                content = content.replace('**', '').replace('*', '').replace('__', '').replace('_', '')
                # --- END MODIFICATION ---

                # Split long lines and handle encoding
                for line in content.splitlines():
                    if line.strip():
                        # Clean line for PDF (remove problematic characters)
                        clean_line = line.encode('latin-1', 'ignore').decode('latin-1')
                        try:
                            pdf.multi_cell(0, 5, clean_line)
                        except:
                            # Fallback for problematic characters
                            pdf.multi_cell(0, 5, "Content contains unsupported characters")
                        pdf.ln(1)
                pdf.ln(3)

        # Save to temp file
        temp_path = os.path.join(tempfile.gettempdir(), file_name)
        pdf.output(temp_path)

        print(f"PDF generated: {temp_path}")
        print(f"PDF exists: {os.path.exists(temp_path)}")
        print(f"PDF size: {os.path.getsize(temp_path)} bytes")

        # Upload to SeaweedFS
        with open(temp_path, 'rb') as pdf_file:
            files = {'file': (file_name, pdf_file, 'application/pdf')}
            response = requests.post(f"http://localhost:8888/seaweedfs/{file_name}", files=files)

            if response.status_code == 201:
                pdf_url = f"http://localhost:8888/seaweedfs/{file_name}"
                print(f"PDF uploaded successfully: {pdf_url}")

                # Clean up temp file
                try:
                    os.remove(temp_path)
                except:
                    pass

                return pdf_url
            else:
                print(f"Failed to upload PDF: {response.status_code}")
                return None

    except Exception as e:
        print(f"PDF generation error: {e}")
        return None