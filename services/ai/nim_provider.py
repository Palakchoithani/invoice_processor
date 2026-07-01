import os
from openai import OpenAI
from services.ai.base_provider import BaseProvider, EXTRACTION_PROMPT

class NimProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise EnvironmentError("NVIDIA_API_KEY not found")
        
        # Auto-prepend nvapi- prefix if missing
        if not self.api_key.startswith("nvapi-"):
            self.api_key = "nvapi-" + self.api_key
            
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key,
        )
        self.model = "meta/llama-3.1-70b-instruct"

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

    def recover_invoice(self, invoice_text: str, printed_total: float, calculated_total: float, gap: float) -> dict:
        from services.ai.base_provider import RECOVERY_PROMPT
        prompt = RECOVERY_PROMPT.format(printed_total=printed_total, calculated_total=calculated_total, gap=gap)
        prompt += f"\n\n{invoice_text}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        
        raw_text = response.choices[0].message.content
        return self.parse_json_response(raw_text)
