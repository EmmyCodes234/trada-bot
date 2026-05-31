from config import settings
from typing import Optional


class RiskManager:
    def check_trade(
        self,
        signal: str,
        confidence: int,
        risk: str,
        balance: float,
        current_price: float,
        suggested_stop: Optional[float] = None,
        atr: Optional[float] = None,
        regime: Optional[str] = None,
    ) -> tuple[bool, str]:
        if confidence < 60:
            return False, f"Confidence too low ({confidence}%)"

        if risk == "HIGH" and signal in ("BUY", "SELL"):
            return False, "Risk level too high for trade"

        if regime == "volatile":
            max_vol_pos = balance * (settings.max_position_size_pct / 200)
            if max_vol_pos < 1:
                return False, f"Volatile market: position too small (${max_vol_pos:.2f})"
        elif regime == "ranging":
            return False, "Ranging market: no clear direction"

        max_position = balance * (settings.max_position_size_pct / 100)
        if max_position < 1:
            return False, f"Balance too low (${balance:.2f})"

        if suggested_stop and current_price > 0:
            risk_pct = abs(current_price - suggested_stop) / current_price * 100
            if risk_pct > settings.stop_loss_pct:
                return False, f"Stop loss ({risk_pct:.1f}%) exceeds max ({settings.stop_loss_pct}%)"

        return True, "Trade approved"

    def calculate_size(self, balance: float, price: float, atr: Optional[float] = None, regime: Optional[str] = None) -> float:
        base_pct = settings.max_position_size_pct

        if regime == "volatile":
            base_pct = base_pct / 2
        elif regime == "trending":
            base_pct = base_pct * 1.2

        if atr and price > 0:
            volatility_ratio = atr / price
            if volatility_ratio > 0.05:
                base_pct = base_pct * 0.5
            elif volatility_ratio > 0.03:
                base_pct = base_pct * 0.75

        max_position = balance * (base_pct / 100)
        quantity = max_position / price if price > 0 else 0
        return quantity
