import httpx
from config import settings


MESSAGES_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "qwen3-max",
    "mimo-v2.5-pro",
]


class OpenModelClient:
    def __init__(self):
        self.api_key = settings.openmodel_api_key
        self.base_url = settings.openmodel_base_url

    async def chat(self, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": model,
            "system": system_prompt,
            "max_tokens": 2048,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
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
            if resp.status_code == 404:
                raise RuntimeError(f"Model '{model}' not available on this account")
            resp.raise_for_status()
            data = resp.json()
            for block in data["content"]:
                if block.get("type") == "text":
                    return block["text"]
            raise RuntimeError(f"No text in response: {data}")

    async def chat_ensemble(self, models: list[str], system_prompt: str, user_prompt: str) -> list[dict]:
        results = []
        for model in models:
            try:
                text = await self.chat(model, system_prompt, user_prompt, temperature=0.3)
                results.append({"model": model, "text": text, "error": None})
            except Exception as e:
                results.append({"model": model, "text": None, "error": str(e)})
        return results
