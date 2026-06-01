import json
import os
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

STATE_FILE = "autotrade_state.json"

DEFAULT_CONFIDENCE_THRESHOLD = 75
DEFAULT_MAX_DAILY_TRADES = 5


class AutoTrader:
    def __init__(self):
        self.enabled: bool = False
        self.confidence_threshold: int = DEFAULT_CONFIDENCE_THRESHOLD
        self.max_daily_trades: int = DEFAULT_MAX_DAILY_TRADES
        self._today_trades: int = 0
        self._today: Optional[str] = None
        self._load()

    def _load(self):
        if not os.path.exists(STATE_FILE):
            self._save()
            return
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            self.enabled = data.get("enabled", False)
            self.confidence_threshold = data.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
            self.max_daily_trades = data.get("max_daily_trades", DEFAULT_MAX_DAILY_TRADES)
            self._today = data.get("today")
            self._today_trades = data.get("today_trades", 0)
            if self._today != str(date.today()):
                self._today_trades = 0
                self._today = str(date.today())
                self._save()
        except Exception as e:
            logger.warning(f"Failed to load autotrade state: {e}")

    def _save(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "enabled": self.enabled,
                    "confidence_threshold": self.confidence_threshold,
                    "max_daily_trades": self.max_daily_trades,
                    "today": self._today or str(date.today()),
                    "today_trades": self._today_trades,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save autotrade state: {e}")

    def can_trade(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Auto-trade is disabled"
        if self._today != str(date.today()):
            self._today_trades = 0
            self._today = str(date.today())
            self._save()
        if self._today_trades >= self.max_daily_trades:
            return False, f"Daily trade limit reached ({self._today_trades}/{self.max_daily_trades})"
        return True, "OK"

    def record_trade(self):
        if self._today != str(date.today()):
            self._today_trades = 0
            self._today = str(date.today())
        self._today_trades += 1
        self._save()

    def enable(self, threshold: Optional[int] = None, max_daily: Optional[int] = None):
        self.enabled = True
        if threshold is not None:
            self.confidence_threshold = max(1, min(100, threshold))
        if max_daily is not None:
            self.max_daily_trades = max(1, max_daily)
        self._save()

    def disable(self):
        self.enabled = False
        self._save()

    def status(self) -> str:
        lines = []
        if self.enabled:
            lines.append("Auto-trade: ON")
            lines.append(f"Min confidence: {self.confidence_threshold}%")
            lines.append(f"Daily limit: {self._today_trades}/{self.max_daily_trades}")
        else:
            lines.append("Auto-trade: OFF")
        return "\n".join(lines)


auto_trader = AutoTrader()
