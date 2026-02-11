import os
from google import genai



client = genai.Client(api_key="AIzaSyC-Tcvx1QGpY73jkfrLSdxfTF_P1C2FqXo")


class GeminiClient:
    def __init__(self, model: str = "gemini-3-flash-preview"):
        self.model = model

    def generate(self, system_prompt: str, user_text: str) -> str:
        """
        Генерация текста через Gemini.
        Возвращает ТОЛЬКО текст ответа модели.
        """

        # 🔹 Склеиваем system + user в ОДНУ строку
        prompt = f"""{system_prompt}
                ---
                ТЕКСТ:
                {user_text}
                """

        response = client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        # Gemini SDK стабильно отдаёт .text
        return response.text.strip()
