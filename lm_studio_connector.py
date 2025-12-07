import requests
import logging

logger = logging.getLogger(__name__)

class LMStudioConnector:
    def __init__(self, model_name="openai/gpt-oss-20b", host="http://127.0.0.1:1234"):
        self.model_name = model_name
        self.host = host
        # Попытка загрузить модель при инициализации
        self.load_model()

    def load_model(self):
        url = f"{self.host}/v1/models"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            models = resp.json().get("data", [])
            available = any(m["id"] == self.model_name for m in models)
            if not available:
                raise Exception(f"Model '{self.model_name}' not found on LM Studio server.")
        except Exception as e:
            raise Exception(f"Ошибка загрузки модели: {e}")

    def generate_text(self, prompt: str) -> str:
        data = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }
        url = f"{self.host}/v1/chat/completions"
        try:
            resp = requests.post(url, json=data, timeout=30000)
            resp.raise_for_status()
            rj = resp.json()
            choices = rj.get("choices", [])
            if not choices:
                return ""
            return choices[0]["message"]["content"]
        except Exception as e:
            return f"<ERROR>LM Studio error: {str(e)}"
