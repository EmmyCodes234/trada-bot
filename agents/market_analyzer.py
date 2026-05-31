from utils.openmodel_client import OpenModelClient
from typing import Optional
import json

ANALYSIS_SYSTEM_PROMPT = """You are a professional trading analyst. Analyze the market data provided and give a clear recommendation.

Return your analysis as a JSON object with exactly these fields:
{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0-100,
  "reasoning": "brief explanation of your reasoning",
  "risk": "LOW" | "MEDIUM" | "HIGH",
  "suggested_entry": number or null,
  "stop_loss": number or null,
  "take_profit": number or null
}

Be conservative. Only give BUY/SELL signals when you have strong conviction.
Consider: trend, support/resistance, volume, volatility, moving averages."""


class MarketAnalyzer:
    def __init__(self):
        self._ai = OpenModelClient()

    async def analyze(self, symbol: str, market_type: str, data_summary: dict) -> Optional[dict]:
        if not data_summary:
            return None

        prompt = self._build_prompt(symbol, market_type, data_summary)
        try:
            result = await self._ai.chat(ANALYSIS_SYSTEM_PROMPT, prompt)
            cleaned = result.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(cleaned)
        except Exception:
            return None

    def _build_prompt(self, symbol: str, market_type: str, data: dict) -> str:
        lines = [
            f"Symbol: {symbol}",
            f"Market Type: {market_type}",
            f"Current Price: {data.get('current_price', 'N/A')}",
            f"24h Change: {data.get('change_pct', 'N/A')}%",
            f"Period High: {data.get('period_high', 'N/A')}",
            f"Period Low: {data.get('period_low', 'N/A')}",
            f"Avg Volume: {data.get('avg_volume', 'N/A')}",
            f"SMA(7): {data.get('sma_7', 'N/A')}",
            f"SMA(21): {data.get('sma_21', 'N/A')}",
            f"Data Points: {data.get('period', 'N/A')}",
        ]
        return "\n".join(lines)
