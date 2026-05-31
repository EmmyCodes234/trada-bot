from .base import BaseExchange, OrderResult, Position
from config import settings
from typing import Optional
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data import StockHistoricalDataClient, StockBarsRequest
from alpaca.data.timeframe import TimeFrame


class AlpacaPaperExchange(BaseExchange):
    def __init__(self):
        self._client = TradingClient(
            api_key=settings.alpaca_api_key or "",
            secret_key=settings.alpaca_secret_key or "",
            paper=settings.alpaca_paper,
        )
        self._data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key or "",
            secret_key=settings.alpaca_secret_key or "",
        )

    def get_balance(self, currency: str = "USD") -> float:
        account = self._client.get_account()
        return float(account.cash)

    def get_position(self, symbol: str) -> Optional[Position]:
        try:
            pos = self._client.get_open_position(symbol)
            return Position(
                symbol=symbol,
                quantity=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl_pct=float(pos.unrealized_pnlpc),
            )
        except Exception:
            return None

    def get_all_positions(self) -> list[Position]:
        try:
            positions = self._client.get_all_positions()
            result = []
            for p in positions:
                result.append(Position(
                    symbol=p.symbol,
                    quantity=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl_pct=float(p.unrealized_pnlpc),
                ))
            return result
        except Exception:
            return []

    def market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(req)
        return OrderResult(
            order_id=str(order.id),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=float(order.limit_price) if order.limit_price else None,
            status=order.status.value,
            filled_quantity=float(order.filled_qty) if order.filled_qty else 0.0,
        )

    def limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> OrderResult:
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = LimitOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=order_side,
            limit_price=price,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(req)
        return OrderResult(
            order_id=str(order.id),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=float(order.limit_price) if order.limit_price else None,
            status=order.status.value,
            filled_quantity=float(order.filled_qty) if order.filled_qty else 0.0,
        )
