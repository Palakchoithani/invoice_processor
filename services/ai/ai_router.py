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

    def extract_with_consensus(self, invoice_text: str, file_name: str) -> dict:
        """
        Routes the extraction request through the priority queue with Real-Time Validation.
        If a provider fails mathematical validation, buffers it and tries the next.
        If all providers fail, runs the Cross-Model Consensus Algorithm.
        """
        from services.parser import parse_invoice, MismatchException
        
        if not invoice_text.strip():
            raise ValueError("Empty invoice text provided to Router.")
            
        failed_results = []
        
        for provider_name in self.priority:
            if provider_name not in self.providers:
                continue
                
            provider = self.providers[provider_name]
            log_info(f"Trying {provider_name.capitalize()}...")
            
            try:
                start_time = time.time()
                raw_data = self._attempt_extraction(provider, invoice_text)
                elapsed = time.time() - start_time
                
                raw_data["provider"] = provider_name
                
                # Real-Time Validation
                try:
                    # We pass recovery_pass=False so it throws MismatchException on math failure
                    invoice = parse_invoice(raw_data, file_name, recovery_pass=False)
                    
                    # Validate required fields
                    if not invoice.invoice_number and not invoice.vendor_name:
                        raise ValueError("Missing critical fields (invoice_number, vendor_name)")
                        
                    log_info(f"Success. ({provider_name.capitalize()}) - Validated perfectly in {elapsed:.2f}s")
                    return raw_data
                    
                except (MismatchException, ValueError) as ve:
                    log_warning(f"{provider_name.capitalize()} extracted successfully but failed Math/Validation: {ve}")
                    raw_data["validation_error"] = str(ve)
                    failed_results.append(raw_data)
                    continue
                
            except Exception as e:
                log_warning(f"{provider_name.capitalize()} API failed: {e}")
                continue
                
        # If we reach here, ALL providers either API-failed or Math-failed.
        if not failed_results:
            log_error("All available AI providers failed completely.")
            raise RuntimeError("AI extraction failed: All providers exhausted or unavailable.")
            
        if len(failed_results) == 1:
            log_info("Only one provider succeeded (but failed math). Returning it for OCR Recovery.")
            return failed_results[0]
            
        # MULTI-MODEL CONSENSUS ALGORITHM
        log_warning("All providers failed mathematical validation. Activating Consensus Engine.")
        consensus_data = self._build_consensus(failed_results)
        consensus_data["provider"] = "Consensus-Hybrid"
        return consensus_data

    def _build_consensus(self, results: list) -> dict:
        """
        Cross-references financial fields across multiple failed AI outputs.
        If 2+ models agree, locks in the value.
        Uses the model with the fewest missing fields as the base skeleton.
        """
        import statistics
        
        # 1. Determine base skeleton by scoring missing keys
        def score_dict(d):
            score = 0
            for k, v in d.items():
                if v is not None and v != "" and v != []:
                    score += 1
            return score
            
        best_result = max(results, key=score_dict)
        merged = dict(best_result) # clone
        
        # 2. Consensus on numerical fields
        numerical_fields = ["subtotal", "tax_amount", "discount_amount", "shipping_charges", 
                            "packing_charges", "handling_charges", "insurance_charges", 
                            "other_charges", "round_off", "total_amount"]
                            
        for field in numerical_fields:
            values = []
            for res in results:
                val = res.get(field)
                if val is not None:
                    values.append(float(val))
                    
            if len(values) >= 2:
                try:
                    # Mode requires exact matches.
                    mode_val = statistics.mode(values)
                    merged[field] = mode_val
                except statistics.StatisticsError:
                    # No unique mode (e.g. 3 models gave 3 different answers)
                    # We stick with the best_result's value
                    pass
                    
        # Add consensus log
        if "extraction_logs" not in merged:
            merged["extraction_logs"] = []
        merged["extraction_logs"].append("SYSTEM: Hybrid Output constructed via Cross-Model Consensus")
        
        return merged

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

    def recover_missing_charges(self, invoice_text: str, printed_total: float, calculated_total: float, gap: float) -> dict:
        """
        Routes the recovery request through the priority queue.
        """
        for provider_name in self.priority:
            if provider_name not in self.providers:
                continue
                
            provider = self.providers[provider_name]
            log_info(f"Trying Recovery with {provider_name.capitalize()}...")
            
            try:
                result = self._attempt_recovery(provider, invoice_text, printed_total, calculated_total, gap)
                log_info(f"Recovery Success. ({provider_name.capitalize()})")
                return result
            except Exception as e:
                log_warning(f"Recovery {provider_name.capitalize()} failed. Reason: {e}")
                continue
                
        log_error("All available AI providers failed the recovery pass.")
        raise RuntimeError("AI recovery failed: All providers exhausted or unavailable.")

    @retry(
        stop=stop_after_attempt(2), 
        wait=wait_exponential(multiplier=1, min=2, max=5), 
        reraise=True,
        before_sleep=before_sleep_log(logging.getLogger("uvicorn.error"), logging.WARNING)
    )
    def _attempt_recovery(self, provider, invoice_text: str, printed_total: float, calculated_total: float, gap: float) -> dict:
        return provider.recover_invoice(invoice_text, printed_total, calculated_total, gap)
