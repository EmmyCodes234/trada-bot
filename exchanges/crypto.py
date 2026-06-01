import ccxt
from .base import BaseExchange, OrderResult, Position
from config import settings
from typing import Optional


class BinanceTestnetExchange(BaseExchange):
    def __init__(self):
        self._exchange = ccxt.binance({
            "apiKey": settings.binance_testnet_api_key,
            "secret": settings.binance_testnet_secret,
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
        })
        self._exchange.set_sandbox_mode(True)

    def get_balance(self, currency: str = "USDT") -> float:
        balance = self._exchange.fetch_balance()
        return float(balance.get(currency, {}).get("free", 0))

    def get_position(self, symbol: str) -> Optional[Position]:
        try:
            balance = self._exchange.fetch_balance()
            asset = symbol.replace("/USDT", "").replace("/USD", "")
            qty = float(balance.get(asset, {}).get("free", 0))
            if qty <= 0:
                return None
            ticker = self._exchange.fetch_ticker(symbol)
            return Position(
                symbol=symbol,
                quantity=qty,
                avg_entry_price=0.0,
                current_price=ticker["last"],
                unrealized_pnl_pct=0.0,
            )
        except Exception:
            return None

    def market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        order = self._exchange.create_market_order(symbol, side, quantity)
        return OrderResult(
            order_id=str(order.get("id", "")),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=order.get("price"),
            status=order.get("status", "closed"),
            filled_quantity=float(order.get("filled", 0)),
        )

    def limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> OrderResult:
        order = self._exchange.create_limit_order(symbol, side, quantity, price)
        return OrderResult(
            order_id=str(order.get("id", "")),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=order.get("status", "open"),
            filled_quantity=float(order.get("filled", 0)),
        )
