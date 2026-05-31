import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


def get_stock_data(
    symbol: str,
    interval: str = "1d",
    period: str = "1mo",
) -> Optional[pd.DataFrame]:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        return df
    except Exception:
        return None


def get_crypto_data(
    symbol: str,
    interval: str = "1d",
    limit: int = 30,
) -> Optional[pd.DataFrame]:
    yahoo_symbol = symbol.replace("/USDT", "-USD").replace("/USD", "-USD").split("/")[0] + "-USD"

    try:
        df = get_stock_data(yahoo_symbol, interval="1d", period="2mo")
        if df is not None:
            return df
    except Exception:
        pass

    import ccxt
    try:
        exchange = ccxt.binance()
        timeframe_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
        }
        tf = timeframe_map.get(interval, "1d")
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df
    except Exception:
        return None


def summarize_data(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change_pct = ((latest["close"] - prev["close"]) / prev["close"]) * 100
    high_52w = df["high"].max()
    low_52w = df["low"].min()
    avg_volume = df["volume"].mean()
    return {
        "current_price": round(latest["close"], 4),
        "change_pct": round(change_pct, 2),
        "period_high": round(high_52w, 4),
        "period_low": round(low_52w, 4),
        "avg_volume": round(avg_volume, 0),
        "sma_7": round(df["close"].rolling(7).mean().iloc[-1], 4) if len(df) >= 7 else None,
        "sma_21": round(df["close"].rolling(21).mean().iloc[-1], 4) if len(df) >= 21 else None,
        "period": len(df),
    }
