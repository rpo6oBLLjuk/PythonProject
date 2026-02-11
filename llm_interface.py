# llm_interface.py
class BaseLLMClient:
    def generate(self, system_prompt: str, user_text: str) -> str:
        raise NotImplementedError
