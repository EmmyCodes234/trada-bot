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
    ) -> tuple[bool, str]:
        if confidence < 60:
            return False, f"Confidence too low ({confidence}%)"

        if risk == "HIGH" and signal in ("BUY", "SELL"):
            return False, "Risk level too high for trade"

        max_position = balance * (settings.max_position_size_pct / 100)
        if max_position < 1:
            return False, f"Balance too low (${balance:.2f})"

        if suggested_stop and current_price > 0:
            risk_pct = abs(current_price - suggested_stop) / current_price * 100
            if risk_pct > settings.stop_loss_pct:
                return False, f"Stop loss ({risk_pct:.1f}%) exceeds max ({settings.stop_loss_pct}%)"

        return True, "Trade approved"
