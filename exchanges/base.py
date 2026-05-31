from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: Optional[float]
    status: str
    filled_quantity: float = 0.0


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl_pct: float


class BaseExchange(ABC):
    @abstractmethod
    def get_balance(self, currency: str = "USD") -> float:
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        ...

    def get_all_positions(self) -> List[Position]:
        return []

    @abstractmethod
    def market_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        ...

    @abstractmethod
    def limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> OrderResult:
        ...
