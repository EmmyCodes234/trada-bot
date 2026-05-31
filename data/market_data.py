import yfinance as yf
import pandas as pd
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "XRP": "ripple", "ADA": "cardano", "DOT": "polkadot", "AVAX": "avalanche-2",
    "LINK": "chainlink", "MATIC": "polygon", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "TRX": "tron", "BNB": "binancecoin",
    "NEAR": "near", "OP": "optimism", "ARB": "arbitrum", "PEPE": "pepe",
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

    if coin_id:
        try:
            days = limit
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
            params = {"vs_currency": "usd", "days": str(days)}
            resp = httpx.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(
                    data,
                    columns=["timestamp", "open", "high", "low", "close"],
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                df["volume"] = 0
                logger.info(f"Got {len(df)} rows from CoinGecko for {base}")
                return df
            else:
                logger.warning(f"CoinGecko returned {resp.status_code} for {coin_id}")
        except Exception as e:
            logger.warning(f"CoinGecko failed for {coin_id}: {e}")

    yahoo_symbol = f"{base}-USD"
    try:
        df = yf.Ticker(yahoo_symbol).history(period="2mo", interval="1d")
        if df is not None and not df.empty:
            logger.info(f"Got {len(df)} rows from yfinance for {yahoo_symbol}")
            return df
    except Exception as e:
        logger.warning(f"yfinance crypto fallback failed for {yahoo_symbol}: {e}")

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
