import csv
import os
import json
from datetime import datetime
from typing import Optional

LOG_FILE = "signals.csv"
TRADE_LOG = "trades.csv"


def _ensure_file(path: str, headers: list[str]):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)


def log_signal(
    symbol: str,
    signal: str,
    confidence: int,
    regime: str,
    risk: str,
    price: float,
    agreement: str,
    models_used: int,
    reasoning: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
):
    _ensure_file(LOG_FILE, [
        "timestamp", "symbol", "signal", "confidence", "regime",
        "risk", "price", "agreement", "models", "stop_loss",
        "take_profit", "reasoning",
    ])
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.utcnow().isoformat(),
            symbol, signal, confidence, regime,
            risk, price, agreement, models_used,
            stop_loss or "", take_profit or "",
            reasoning.replace("\n", " | "),
        ])


def log_trade(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    status: str,
    signal: str,
    confidence: int,
    order_id: Optional[str] = None,
    error: Optional[str] = None,
):
    _ensure_file(TRADE_LOG, [
        "timestamp", "symbol", "side", "quantity", "price",
        "status", "signal", "confidence", "order_id", "error",
    ])
    with open(TRADE_LOG, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.utcnow().isoformat(),
            symbol, side, quantity, price,
            status, signal, confidence,
            order_id or "", error or "",
        ])


def get_stats() -> str:
    if not os.path.exists(LOG_FILE):
        return "No signals logged yet"

    lines = []
    with open(LOG_FILE) as f:
        reader = csv.DictReader(f)
        total = 0
        buys = sells = holds = 0
        for row in reader:
            total += 1
            s = row.get("signal", "")
            if s == "BUY": buys += 1
            elif s == "SELL": sells += 1
            else: holds += 1

    lines.append(f"Total signals: {total}")
    lines.append(f"BUY: {buys} | SELL: {sells} | HOLD: {holds}")
    if total > 0:
        actionable = buys + sells
        lines.append(f"Actionable rate: {actionable}/{total} ({actionable/total*100:.0f}%)")

    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG) as f:
            reader = csv.DictReader(f)
            exec_total = sum(1 for _ in reader)
        lines.append(f"Executed trades: {exec_total}")

    return "\n".join(lines)
