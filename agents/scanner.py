import asyncio
import logging
from typing import Optional

from agents.ensemble_analyzer import EnsembleAnalyzer
from data.market_data import get_multi_timeframe_data

logger = logging.getLogger(__name__)

SCAN_SYMBOLS = ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK", "DOT", "NEAR"]
MAX_CONCURRENT = 3


class MarketScanner:
    def __init__(self):
        self._analyzer = EnsembleAnalyzer()

    async def scan(self) -> list[dict]:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def _analyze(symbol: str) -> Optional[dict]:
            async with sem:
                try:
                    sym = f"{symbol}/USDT"
                    multi_data = get_multi_timeframe_data(sym, "crypto")
                    if not multi_data:
                        return None
                    result = await self._analyzer.analyze_all(sym, "crypto", multi_data)
                    if not result:
                        return None
                    price = 0
                    for df in multi_data.values():
                        if df is not None and not df.empty:
                            price = df["close"].iloc[-1]
                            break
                    return {
                        "symbol": symbol,
                        "signal": result.get("signal", "HOLD"),
                        "confidence": result.get("confidence", 0),
                        "regime": result.get("regime", "?"),
                        "risk": result.get("risk", "?"),
                        "agreement": result.get("agreement", "?"),
                        "price": price,
                    }
                except Exception as e:
                    logger.warning(f"Scan failed for {symbol}: {e}")
                    return None

        tasks = [_analyze(s) for s in SCAN_SYMBOLS]
        results = await asyncio.gather(*tasks)
        results = [r for r in results if r is not None]

        results.sort(key=lambda r: (
            {"BUY": 0, "SELL": 1, "HOLD": 2}.get(r["signal"], 3),
            -r["confidence"],
        ))

        return results


scanner = MarketScanner()
