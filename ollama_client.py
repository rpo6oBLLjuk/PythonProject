from __future__ import annotations

import json
import requests
from typing import Iterator, Optional, Dict, Any


class OllamaClient:
    def __init__(
        self,
        model: str = "gpt-oss:20b",
        base_url: str = "http://localhost:11434",
        timeout: int = 600,
        default_params: Optional[Dict[str, Any]] = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.default_params = {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_ctx": 8192,
        }

        if default_params:
            self.default_params.update(default_params)

    # ------------------------------------------------------------
    # Базовый запрос (непотоковый)
    # ------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        **params,
    ) -> str:
        #Выполняет одиночную генерацию и возвращает весь ответ строкой.
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **self.default_params,
            **params,
        }

        if system:
            payload["system"] = system

        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )

        resp.raise_for_status()
        data = resp.json()

        return data.get("response", "")

    # ------------------------------------------------------------
    # Потоковая генерация (для больших текстов)
    # ------------------------------------------------------------
    def generate_stream(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        **params,
    ) -> Iterator[str]:
        #Генерация с потоковой выдачей (yield по кускам текста).

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            **self.default_params,
            **params,
        }

        if system:
            payload["system"] = system

        with requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            stream=True,
            timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line.decode("utf-8"))

                if chunk.get("done"):
                    break

                yield chunk.get("response", "")

    # ------------------------------------------------------------
    # Служебные методы
    # ------------------------------------------------------------
    def ping(self) -> bool:
        """
        Проверка доступности Ollama.
        """
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """
        Возвращает список доступных локальных моделей.
        """
        r = requests.get(f"{self.base_url}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
