import requests


class OllamaClient:
    def __init__(self, model: str = "gpt-oss:20b"):
        self.model = model
        self.url = "http://localhost:11434/api/chat"

    def generate(self, system_prompt: str, user_text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            "think": False,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "top_p": 0.9
            }
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=60 * 20
        )
        response.raise_for_status()

        data = response.json()

        # Ollama chat возвращает message → content
        return data["message"]["content"]
