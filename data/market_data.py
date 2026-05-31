import yfinance as yf
import pandas as pd
import httpx
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
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}")
        return None


def get_crypto_data(
    symbol: str,
    interval: str = "1d",
    limit: int = 30,
) -> Optional[pd.DataFrame]:
    base = symbol.split("/")[0].upper()
    coin_id = COINGECKO_IDS.get(base)

    headers = {"User-Agent": "TradaBot/1.0"}

    try:
        df = yf.Ticker(f"{base}-USD").history(period="2mo", interval="1d")
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            logger.info(f"Got {len(df)} rows from yfinance for {base}-USD")
            return df
    except Exception as e:
        logger.warning(f"yfinance failed for {base}-USD: {e}")

    if coin_id:
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": str(limit)}
            resp = httpx.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df.set_index("timestamp", inplace=True)
                    df["volume"] = 0
                    logger.info(f"Got {len(df)} rows from CoinGecko for {base}")
                    return df
            logger.warning(f"CoinGecko failed: status={resp.status_code}, body={resp.text[:200]}")
        except Exception as e:
            logger.warning(f"CoinGecko error for {coin_id}: {e}")

    try:
        import ccxt
        ex = ccxt.binance()
        ohlcv = ex.fetch_ohlcv(symbol, timeframe="1d", limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        logger.info(f"Got {len(df)} rows from Binance for {symbol}")
        return df
    except Exception as e:
        logger.warning(f"Binance failed for {symbol}: {e}")

    return None


def summarize_data(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change_pct = ((latest["close"] - prev["close"]) / prev["close"]) * 100
    high_52w = df["high"].max()
    low_52w = df["low"].min()
    avg_volume = df["volume"].mean() if "volume" in df and df["volume"].sum() > 0 else 0
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
