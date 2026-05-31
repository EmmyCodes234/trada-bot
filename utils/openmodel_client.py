import httpx
from config import settings


class OpenModelClient:
    def __init__(self):
        self.api_key = settings.openmodel_api_key
        self.base_url = settings.openmodel_base_url
        self.model = settings.analysis_model

    async def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
