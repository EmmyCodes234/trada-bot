import httpx
from config import settings


class OpenModelClient:
    def __init__(self):
        self.api_key = settings.openmodel_api_key
        self.base_url = settings.openmodel_base_url
        self.model = settings.analysis_model

    async def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        url = f"{self.base_url}/v1/responses"
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code == 404:
                raise RuntimeError(
                    f"OpenModel API returned 404. Make sure OPENMODEL_API_KEY is set correctly "
                    f"in Railway env vars. Got key: '{self.api_key[:8]}...'"
                )
            resp.raise_for_status()
            data = resp.json()
            return data["output"][0]["content"][0]["text"]
