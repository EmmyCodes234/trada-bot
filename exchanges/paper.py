import json
import os
import logging
from datetime import datetime
from typing import Optional, List
from .base import BaseExchange, OrderResult, Position
import yfinance as yf

logger = logging.getLogger(__name__)

PAPER_FILE = "paper_portfolio.json"
INITIAL_BALANCE = 10000.0
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "DOT", "AVAX", "LINK", "MATIC", "UNI", "ATOM", "LTC", "BCH", "TRX", "BNB", "NEAR", "OP", "ARB"}


class PaperExchange(BaseExchange):
    def __init__(self):
        self.balance: float = INITIAL_BALANCE
        self.holdings: dict[str, float] = {}
        self.trades: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(PAPER_FILE):
            try:
                with open(PAPER_FILE) as f:
                    data = json.load(f)
                    self.balance = data.get("balance", INITIAL_BALANCE)
                    self.holdings = data.get("holdings", {})
                    self.trades = data.get("trades", [])
            except Exception as e:
                logger.warning(f"Failed to load paper portfolio: {e}")

    def _save(self):
        try:
            with open(PAPER_FILE, "w") as f:
                json.dump({
                    "balance": round(self.balance, 2),
                    "holdings": {k: round(v, 6) for k, v in self.holdings.items()},
                    "trades": self.trades,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save paper portfolio: {e}")

    def _get_price(self, symbol: str) -> float:
        base = symbol.split("/")[0].upper()
        try:
            ticker = yf.Ticker(f"{base}-USD")
            data = ticker.history(period="1d", interval="5m")
            if not data.empty:
                return float(data["Close"].iloc[-1])
            data = ticker.history(period="5d", interval="1d")
            if not data.empty:
                return float(data["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"PaperExchange: yfinance price failed for {base}: {e}")
        return 0.0

    def reset(self, balance: float = INITIAL_BALANCE):
        self.balance = balance
        self.holdings = {}
        self.trades = []
        self._save()

    def get_balance(self, currency: str = "USDT") -> float:
        total = self.balance
        for asset, qty in self.holdings.items():
            if qty > 0:
                price = self._get_price(f"{asset}/USDT")
                total += qty * price
        return total

    def get_position(self, symbol: str) -> Optional[Position]:
        asset = symbol.split("/")[0]
        qty = self.holdings.get(asset, 0)
        if qty <= 0:
            return None
        price = self._get_price(symbol)
        t = next((t for t in reversed(self.trades) if t["symbol"].startswith(asset) and t["side"] == "buy"), None)
        avg_entry = t["price"] if t else price
        pnl_pct = ((price - avg_entry) / avg_entry * 100) if avg_entry > 0 else 0
        return Position(
            symbol=symbol,
            quantity=qty,
            avg_entry_price=avg_entry,
            current_price=price,
            unrealized_pnl_pct=round(pnl_pct, 2),
        )

    def get_all_positions(self) -> List[Position]:
        positions = []
        for asset, qty in list(self.holdings.items()):
            if qty > 0:
                pos = self.get_position(f"{asset}/USDT")
                if pos:
                    positions.append(pos)
        return positions

    def market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        price = self._get_price(symbol)
        if price <= 0:
            raise Exception(f"Could not get price for {symbol}")
        asset = symbol.split("/")[0]
        cost = quantity * price

        if side == "buy":
            if cost > self.balance:
                max_qty = self.balance / price
                raise Exception(
                    f"Insufficient USDT. Have ${self.balance:.2f}, need ${cost:.2f}. "
                    f"Max {asset}: {max_qty:.4f}"
                )
            self.balance -= cost
            self.holdings[asset] = round(self.holdings.get(asset, 0) + quantity, 6)
        else:
            held = self.holdings.get(asset, 0)
            if quantity > held:
                raise Exception(f"Insufficient {asset}. Have {held:.4f}, want {quantity:.4f}")
            self.holdings[asset] = round(held - quantity, 6)
            self.balance += cost
            if self.holdings[asset] < 0.000001:
                del self.holdings[asset]

        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "side": side,
            "quantity": round(quantity, 6),
            "price": round(price, 4),
            "cost": round(cost, 2),
        }
        self.trades.append(trade)
        self._save()

        return OrderResult(
            order_id=f"paper_{len(self.trades)}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status="closed",
            filled_quantity=quantity,
        )

    def limit_order(self, symbol: str, side: str, quantity: float, price: float) -> OrderResult:
        raise NotImplementedError("Limit orders not supported in paper exchange")
