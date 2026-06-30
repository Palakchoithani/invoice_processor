import os
from groq import Groq
from services.ai.base_provider import BaseProvider, EXTRACTION_PROMPT

class GroqProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise EnvironmentError("GROQ_API_KEY not found")
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"

    def extract_invoice(self, invoice_text: str) -> dict:
        prompt = EXTRACTION_PROMPT + f"\n\n{invoice_text}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        
        raw_text = response.choices[0].message.content
        return self.parse_json_response(raw_text)
