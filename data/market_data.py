import yfinance as yf
import pandas as pd
import httpx
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "XRP": "ripple", "ADA": "cardano", "DOT": "polkadot",
    "LINK": "chainlink", "MATIC": "polygon", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "TRX": "tron", "BNB": "binancecoin",
    "NEAR": "near", "OP": "optimism", "ARB": "arbitrum",
}

TIMEFRAMES = {
    "1h": {"yf_interval": "1h", "yf_period": "1mo", "cg_days": 7, "limit": 24},
    "4h": {"yf_interval": "1h", "yf_period": "2mo", "cg_days": 14, "limit": 48},
    "1d": {"yf_interval": "1d", "yf_period": "3mo", "cg_days": 60, "limit": 60},
}


def get_stock_data(symbol: str, interval: str = "1d", period: str = "1mo") -> Optional[pd.DataFrame]:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}")
        return None


def get_crypto_data(symbol: str, interval: str = "1d", limit: int = 60) -> Optional[pd.DataFrame]:
    base = symbol.split("/")[0].upper()
    coin_id = COINGECKO_IDS.get(base)

    try:
        tf_config = TIMEFRAMES.get(interval, TIMEFRAMES["1d"])
        df = yf.Ticker(f"{base}-USD").history(period=tf_config["yf_period"], interval=tf_config["yf_interval"])
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            logger.info(f"Got {len(df)} rows from yfinance for {base}-USD ({interval})")
            return df
    except Exception as e:
        logger.warning(f"yfinance failed for {base}-USD ({interval}): {e}")

    if coin_id:
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": str(tf_config["cg_days"])}
            resp = httpx.get(url, params=params, headers={"User-Agent": "TradaBot/1.0"}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df.set_index("timestamp", inplace=True)
                    df["volume"] = 0
                    return df
            logger.warning(f"CoinGecko {interval}: status={resp.status_code}")
        except Exception as e:
            logger.warning(f"CoinGecko error: {e}")

    return None


def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if df is None or len(df) < period + 1:
        return None
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    tr = np.maximum(high[1:] - low[1:],
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1]))
    atr = np.mean(tr[-period:])
    return float(atr)


def detect_regime(df: pd.DataFrame) -> str:
    if df is None or len(df) < 20:
        return "unknown"
    close = df["close"].values[-20:]
    sma20 = np.mean(close)
    std20 = np.std(close)
    cvs = std20 / sma20 if sma20 > 0 else 0

    pct_changes = np.abs(np.diff(close) / close[:-1])
    avg_volatility = np.mean(pct_changes) * 100

    n = len(close)
    up_sum = sum(1 for i in range(1, n) if close[i] > close[i-1])
    trend_strength = abs(up_sum / (n - 1) - 0.5) * 2

    if cvs > 0.05 or avg_volatility > 2:
        return "volatile"
    if trend_strength > 0.6:
        return "trending"
    return "ranging"


def get_multi_timeframe_data(symbol: str, market_type: str) -> dict:
    result = {}
    for tf in TIMEFRAMES:
        tf_config = TIMEFRAMES[tf]
        if market_type == "crypto":
            df = get_crypto_data(symbol, interval=tf, limit=tf_config["limit"])
        else:
            df = get_stock_data(symbol, interval=tf_config["yf_interval"], period=tf_config["yf_period"])
        if df is not None:
            result[tf] = df
    return result


def summarize_data(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change_pct = ((latest["close"] - prev["close"]) / prev["close"]) * 100
    period_high = df["high"].max()
    period_low = df["low"].min()
    avg_volume = df["volume"].mean() if "volume" in df and df["volume"].sum() > 0 else 0
    atr = calculate_atr(df)
    regime = detect_regime(df)
    return {
        "current_price": round(latest["close"], 4),
        "change_pct": round(change_pct, 2),
        "period_high": round(period_high, 4),
        "period_low": round(period_low, 4),
        "avg_volume": round(avg_volume, 0),
        "sma_7": round(df["close"].rolling(7).mean().iloc[-1], 4) if len(df) >= 7 else None,
        "sma_21": round(df["close"].rolling(21).mean().iloc[-1], 4) if len(df) >= 21 else None,
        "atr": round(atr, 4) if atr else None,
        "regime": regime,
        "period": len(df),
    }
