import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
from services.logger import log_info, log_error, log_warning

# Import Providers
from services.ai.groq_provider import GroqProvider
from services.ai.openrouter_provider import OpenRouterProvider
from services.ai.nim_provider import NimProvider

class AIRouter:
    def __init__(self):
        # We try to initialize providers. If a key is missing, that provider is skipped.
        self.providers = {}
        
        # Priority mapping
        provider_classes = {
            "groq": GroqProvider,
            "openrouter": OpenRouterProvider,
            "nim": NimProvider
        }
        
        # Load available providers
        for name, provider_cls in provider_classes.items():
            try:
                self.providers[name] = provider_cls()
            except EnvironmentError:
                log_warning(f"Provider '{name}' skipped: API key missing.")
        
        # Hardcoded default priority list. This can be moved to a yaml file.
        self.priority = ["groq", "openrouter", "nim"]

    def route_extraction(self, invoice_text: str) -> dict:
        """
        Routes the extraction request through the priority queue.
        Falls back to the next provider on consistent failure.
        """
        if not invoice_text.strip():
            raise ValueError("Empty invoice text provided to Router.")
            
        for provider_name in self.priority:
            if provider_name not in self.providers:
                continue
                
            provider = self.providers[provider_name]
            log_info(f"Trying {provider_name.capitalize()}...")
            
            try:
                start_time = time.time()
                # Run the extraction with exponential backoff on transient errors
                result = self._attempt_extraction(provider, invoice_text)
                elapsed = time.time() - start_time
                
                log_info(f"Success. ({provider_name.capitalize()}) - Response time: {elapsed:.2f}s")
                return result
                
            except Exception as e:
                # If it still fails after 2 retries, fallback to the next provider
                log_warning(f"{provider_name.capitalize()} failed after retries. Reason: {e}")
                log_info(f"Switching to next provider...")
                continue
                
        # If the loop finishes without returning, all providers failed.
        log_error("All available AI providers failed.")
        raise RuntimeError("AI extraction failed: All providers exhausted or unavailable.")

    # Retry decorator: retries twice (stop_after_attempt(3) means 1 initial try + 2 retries)
    # Uses exponential backoff: wait 2^x * 1 seconds between each retry (max 10s)
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        reraise=True,
        before_sleep=before_sleep_log(logging.getLogger("uvicorn.error"), logging.WARNING)
    )
    def _attempt_extraction(self, provider, invoice_text: str) -> dict:
        """
        Single extraction attempt wrapped in Tenacity for exponential backoff retries.
        """
        return provider.extract_invoice(invoice_text)
