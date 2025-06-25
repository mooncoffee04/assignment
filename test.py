import os
from google import genai
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env file

api_key = os.getenv("API_KEY")

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="How are you?",
)

print(response.text)