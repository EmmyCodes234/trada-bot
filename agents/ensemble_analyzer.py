import json
import asyncio
import logging
from typing import Optional
from utils.openmodel_client import OpenModelClient
from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional trading analyst. Analyze the market data and give a recommendation.

Return ONLY a JSON object with exactly these fields:
{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0-100,
  "reasoning": "brief explanation",
  "risk": "LOW" | "MEDIUM" | "HIGH",
  "stop_loss": number or null,
  "take_profit": number or null
}

Be conservative. Only BUY/SELL with strong conviction."""


class EnsembleAnalyzer:
    def __init__(self):
        self._client = OpenModelClient()

    def _models(self) -> list[str]:
        raw = settings.ensemble_models
        return [m.strip() for m in raw.split(",") if m.strip()]

    def _build_prompt(self, symbol: str, market_type: str, tf: str, data: dict) -> str:
        return "\n".join([
            f"Symbol: {symbol}",
            f"Market Type: {market_type}",
            f"Timeframe: {tf}",
            f"Regime: {data.get('regime', '?')}",
            f"Price: {data.get('current_price', 'N/A')}",
            f"Change: {data.get('change_pct', 'N/A')}%",
            f"High: {data.get('period_high', 'N/A')}",
            f"Low: {data.get('period_low', 'N/A')}",
            f"Vol: {data.get('avg_volume', 'N/A')}",
            f"SMA7: {data.get('sma_7', 'N/A')}",
            f"SMA21: {data.get('sma_21', 'N/A')}",
            f"ATR: {data.get('atr', 'N/A')}",
        ])

    def _parse(self, text: str) -> Optional[dict]:
        try:
            cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(cleaned)
        except Exception:
            return None

    async def analyze_timeframe(self, symbol: str, market_type: str, tf: str, data: dict) -> Optional[dict]:
        prompt = self._build_prompt(symbol, market_type, tf, data)
        models = self._models()
        responses = await self._client.chat_ensemble(models, SYSTEM_PROMPT, prompt)

        parsed = []
        for r in responses:
            if r["error"]:
                logger.warning(f"{r['model']} on {tf}: {r['error']}")
                continue
            p = self._parse(r["text"])
            if p:
                p["_model"] = r["model"]
                parsed.append(p)

        if not parsed:
            return None

        buys = sum(1 for p in parsed if p.get("signal") == "BUY")
        sells = sum(1 for p in parsed if p.get("signal") == "SELL")
        holds = sum(1 for p in parsed if p.get("signal") == "HOLD")
        n = len(parsed)
        min_agree = settings.min_ensemble_agreement

        if buys >= min_agree and buys > sells and buys > holds:
            signal = "BUY"
            consensus = buys
        elif sells >= min_agree and sells > buys and sells > holds:
            signal = "SELL"
            consensus = sells
        else:
            signal = "HOLD"
            consensus = max(buys, sells, holds)

        avg_confidence = int(sum(p.get("confidence", 0) or 0 for p in parsed) / n)
        risks = [p.get("risk", "MEDIUM") for p in parsed]
        high_risk_count = risks.count("HIGH")

        reasoning_parts = [p.get("reasoning", "?").strip() for p in parsed]
        reasoning = " | ".join(reasoning_parts)

        stop_losses = [p.get("stop_loss") for p in parsed if p.get("stop_loss")]
        take_profits = [p.get("take_profit") for p in parsed if p.get("take_profit")]

        return {
            "signal": signal,
            "confidence": avg_confidence,
            "consensus": f"{consensus}/{n}",
            "models_used": n,
            "reasoning": reasoning,
            "risk": "HIGH" if high_risk_count > n // 2 else ("MEDIUM" if high_risk_count > 0 else "LOW"),
            "stop_loss": sum(stop_losses) / len(stop_losses) if stop_losses else None,
            "take_profit": sum(take_profits) / len(take_profits) if take_profits else None,
        }

    async def analyze_all(self, symbol: str, market_type: str, multi_data: dict) -> dict:
        tasks = []
        for tf, df in multi_data.items():
            summary = _summarize_df(df)
            if summary:
                tasks.append((tf, summary))

        if not tasks:
            return {"signal": "HOLD", "confidence": 0, "reasoning": "No data"}

        tf_results = {}
        for tf, summary in tasks:
            result = await self.analyze_timeframe(symbol, market_type, tf, summary)
            if result:
                tf_results[tf] = result

        if not tf_results:
            return {"signal": "HOLD", "confidence": 0, "reasoning": "All analyses failed"}

        tf_signals = [(tf, r["signal"]) for tf, r in tf_results.items()]
        buy_tfs = [tf for tf, s in tf_signals if s == "BUY"]
        sell_tfs = [tf for tf, s in tf_signals if s == "SELL"]
        hold_tfs = [tf for tf, s in tf_signals if s == "HOLD"]

        if len(buy_tfs) >= 2:
            final_signal = "BUY"
            agreeing = buy_tfs
        elif len(sell_tfs) >= 2:
            final_signal = "SELL"
            agreeing = sell_tfs
        else:
            final_signal = "HOLD"
            agreeing = ["no alignment across timeframes"]
            if hold_tfs:
                agreeing = hold_tfs

        avg_conf = int(sum(r.get("confidence", 0) or 0 for r in tf_results.values()) / len(tf_results))
        reasons = [f"{tf}: {r.get('reasoning','')}" for tf, r in tf_results.items()]
        all_stops = [r["stop_loss"] for r in tf_results.values() if r.get("stop_loss")]
        all_tps = [r["take_profit"] for r in tf_results.values() if r.get("take_profit")]

        regimes = [summary.get("regime", "?") for _, summary in tasks]
        regime_counts = {}
        for r in regimes:
            regime_counts[r] = regime_counts.get(r, 0) + 1
        dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "?"

        return {
            "signal": final_signal,
            "confidence": avg_conf,
            "timeframe_signals": tf_signals,
            "models_used": tf_results.get(list(tf_results.keys())[0], {}).get("models_used", 0),
            "reasoning": "\n".join(reasons),
            "regime": dominant_regime,
            "risk": max((r.get("risk", "LOW") for r in tf_results.values()), key=lambda x: ["LOW", "MEDIUM", "HIGH"].index(x)),
            "stop_loss": sum(all_stops) / len(all_stops) if all_stops else None,
            "take_profit": sum(all_tps) / len(all_tps) if all_tps else None,
            "agreement": f"{len(agreeing)}/{len(tf_results)} timeframes",
        }


def _summarize_df(df) -> Optional[dict]:
    if df is None or df.empty:
        return None
    from data.market_data import summarize_data
    return summarize_data(df)
