from openai import OpenAI


class OpenAIClient:
    def __init__(self, api_key: str = "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", model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.0,
        )

        return response.choices[0].message.content.strip()
