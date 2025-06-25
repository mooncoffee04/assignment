import fitz  # PyMuPDF
import pandas as pd
from PIL import Image
import base64
import mimetypes

def extract_text_from_pdf(uploaded_file):
    pdf_text = ""
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    for page in doc:
        pdf_text += page.get_text()
    return pdf_text

def parse_lab_file(file):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
        return df.to_string(index=False)
    elif file.name.endswith('.pdf'):
        return extract_text_from_pdf(file)
    return None

def encode_image(file_like):
    import base64
    import mimetypes

    filename = getattr(file_like, "name", "file.png")
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_like.seek(0)
    encoded = base64.b64encode(file_like.read()).decode("utf-8")
    return {
        "inline_data": {
            "mime_type": mime_type,
            "data": encoded
        }
    }

