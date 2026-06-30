import os
from openai import OpenAI
from services.ai.base_provider import BaseProvider, EXTRACTION_PROMPT

class OpenRouterProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise EnvironmentError("OPENROUTER_API_KEY not found")
        
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
        )
        self.model = "meta-llama/llama-3.3-70b-instruct"

    def extract_invoice(self, invoice_text: str) -> dict:
        prompt = EXTRACTION_PROMPT + f"\n\n{invoice_text}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2048,
            extra_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "InvoiceProcessor"
            }
        )
        
        raw_text = response.choices[0].message.content
        return self.parse_json_response(raw_text)
