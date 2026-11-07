from utils.llm_client import generate_json

class LLMProviderService:
    """Delegates structured JSON inference to the configured Groq model."""
    def generate_json(self, system: str, prompt: str, model: str | None = None) -> dict:
        return generate_json(system, prompt, model)
