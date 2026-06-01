from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Optional
import logging

from agents.ensemble_analyzer import EnsembleAnalyzer
from agents.risk_manager import RiskManager
from agents.signal_logger import log_signal, log_trade, get_stats
from data.market_data import get_multi_timeframe_data
from exchanges.crypto import BinanceTestnetExchange
from exchanges.stocks import AlpacaPaperExchange
from config import settings

logger = logging.getLogger(__name__)
analyzer = EnsembleAnalyzer()
risk_manager = RiskManager()

CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "DOT", "AVAX", "LINK", "MATIC", "UNI", "ATOM", "LTC", "BCH", "TRX", "BNB", "NEAR", "OP", "ARB"}

HELP_TEXT = (
    "/start — Show menu\n"
    "/analyze <symbol> — Full AI analysis (no trade)\n"
    "/trade <symbol> — Analysis + execute if signal\n"
    "/portfolio — View open positions\n"
    "/balance — Check balances\n"
    "/stats — Signal/trade history\n"
    "/help — Show commands"
)


def _detect_market(symbol: str) -> str:
    base = symbol.split("/")[0].upper()
    if "/" in symbol or base in CRYPTO_SYMBOLS:
        return "crypto"
    return "stocks"


def _normalize_symbol(symbol: str) -> str:
    market = _detect_market(symbol)
    if market == "crypto" and "/" not in symbol:
        symbol = symbol.upper() + "/USDT"
    return symbol.upper()


def _fmt(n: Optional[float], d: int = 4) -> str:
    if n is None:
        return "N/A"
    return f"{n:.{d}f}"


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Trada — AI Trading Agent\n"
        "Powered by OpenModel.ai\n\n"
        "Features:\n"
        "- Multi-model ensemble (3 AI models vote)\n"
        "- Multi-timeframe alignment (1h, 4h, 1d)\n"
        "- Regime detection (trending/ranging/volatile)\n"
        "- Volatility-adjusted position sizing\n"
        "- Signal history tracking\n\n"
        f"{HELP_TEXT}"
    )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /analyze <symbol>\nExample: /analyze BTC or /analyze AAPL")
        return

    symbol = _normalize_symbol(ctx.args[0])
    market = _detect_market(symbol)
    msg = await update.message.reply_text(f"Analyzing {symbol} across 3 models and 3 timeframes...")

    try:
        multi_data = get_multi_timeframe_data(symbol, market)
        if not multi_data:
            await msg.edit_text(f"No data available for {symbol}")
            return

        result = await analyzer.analyze_all(symbol, market, multi_data)
        if not result or result.get("signal") == "HOLD" and result.get("confidence", 0) == 0:
            await msg.edit_text(f"Analysis failed for {symbol}")
            return

        price = 0
        for tf_data in multi_data.values():
            if tf_data is not None and not tf_data.empty:
                price = tf_data["close"].iloc[-1]
                break

        log_signal(
            symbol=symbol,
            signal=result.get("signal", "HOLD"),
            confidence=result.get("confidence", 0),
            regime=result.get("regime", "?"),
            risk=result.get("risk", "?"),
            price=price,
            agreement=result.get("agreement", "?"),
            models_used=result.get("models_used", 0),
            reasoning=result.get("reasoning", ""),
            stop_loss=result.get("stop_loss"),
            take_profit=result.get("take_profit"),
        )

        text = _format_ensemble(symbol, result, price)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"analyze error", exc_info=True)
        await msg.edit_text(f"Error: {type(e).__name__}: {e}")


async def trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /trade <symbol>\nExample: /trade BTC")
        return

    symbol = _normalize_symbol(ctx.args[0])
    market = _detect_market(symbol)
    msg = await update.message.reply_text(f"Analyzing {symbol} for trade...")

    try:
        multi_data = get_multi_timeframe_data(symbol, market)
        if not multi_data:
            await msg.edit_text(f"No data available for {symbol}")
            return

        result = await analyzer.analyze_all(symbol, market, multi_data)
        signal = result.get("signal", "HOLD")

        price = 0
        atr = None
        regime = result.get("regime")
        for tf_data in multi_data.values():
            if tf_data is not None and not tf_data.empty:
                price = tf_data["close"].iloc[-1]
                break

        text = _format_ensemble(symbol, result, price)
        log_signal(symbol, signal, result.get("confidence", 0), regime, result.get("risk", "?"), price,
                   result.get("agreement", "?"), result.get("models_used", 0), result.get("reasoning", ""))

        if signal == "HOLD":
            text += "\n\nNo actionable signal."
            await msg.edit_text(text, parse_mode="Markdown")
            return

        balance = _get_balance(market)
        approved, reason = risk_manager.check_trade(
            signal=signal,
            confidence=result.get("confidence", 0),
            risk=result.get("risk", "MEDIUM"),
            balance=balance,
            current_price=price,
            suggested_stop=result.get("stop_loss"),
            atr=atr,
            regime=regime,
        )

        if not approved:
            text += f"\n\nRisk check: {reason}"
            await msg.edit_text(text, parse_mode="Markdown")
            return

        quantity = risk_manager.calculate_size(balance, price, atr, regime)
        side = "buy" if signal == "BUY" else "sell"

        text += f"\n\nProposed: {side.upper()} {quantity:.4f} {symbol.split('/')[0] if market == 'crypto' else symbol} (~${quantity * price:.2f})"

        keyboard = [[
            InlineKeyboardButton("Execute", callback_data=f"exec|{market}|{symbol}|{side}|{quantity}|{result.get('confidence',0)}|{result.get('signal','?')}"),
            InlineKeyboardButton("Cancel", callback_data="cancel"),
        ]]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"trade error", exc_info=True)
        await msg.edit_text(f"Error: {type(e).__name__}: {e}")


async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Trade cancelled.")
        return

    parts = data.split("|")
    if parts[0] == "exec":
        _, market_type, symbol, side, quantity, confidence, signal = parts[:7]
        quantity = float(quantity)
        confidence = int(confidence)
        try:
            ex = BinanceTestnetExchange() if market_type == "crypto" else AlpacaPaperExchange()
            price = ex.get_balance()
            if side == "buy":
                order = ex.market_order(symbol, "buy", quantity)
            else:
                order = ex.market_order(symbol, "sell", quantity)

            log_trade(symbol, side, quantity, order.price or 0, order.status, signal, confidence, order_id=order.order_id)
            await query.edit_message_text(f"Executed {side.upper()} {quantity:.4f} {symbol} (ID: {order.order_id})")
        except Exception as e:
            log_trade(symbol, side, quantity, 0, "failed", signal, confidence, error=str(e))
            await query.edit_message_text(f"Order failed: {e}")


async def portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Open Positions:\n"]
    try:
        for pos in AlpacaPaperExchange().get_all_positions():
            lines.append(f"{pos.symbol}: {pos.quantity:.2f} @ ${pos.current_price:.2f} ({pos.unrealized_pnl_pct:+.2f}%)")
        if len(lines) == 1:
            lines.append("No open positions.")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Account Balances:\n"]
    try:
        lines.append(f"Alpaca (Stocks): ${AlpacaPaperExchange().get_balance():.2f}")
    except Exception as e:
        logger.error(f"Alpaca balance error: {e}")
        lines.append("Alpaca: not configured")
    try:
        lines.append(f"Binance Testnet: ${BinanceTestnetExchange().get_balance('USDT'):.2f}")
    except Exception as e:
        logger.error(f"Binance balance error: {e}")
        lines.append("Binance: not configured")
    await update.message.reply_text("\n".join(lines))


async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_stats())


def _format_ensemble(symbol: str, result: dict, price: float) -> str:
    signal = result.get("signal", "N/A")
    confidence = result.get("confidence", "N/A")
    regime = result.get("regime", "N/A")
    risk = result.get("risk", "N/A")
    agreement = result.get("agreement", "N/A")
    models = result.get("models_used", "N/A")
    reasoning = result.get("reasoning", "N/A")
    sl = _fmt(result.get("stop_loss"))
    tp = _fmt(result.get("take_profit"))

    tf_lines = ""
    for tf, sig in result.get("timeframe_signals", []):
        tf_lines += f"\n  {tf}: {sig}"

    return (
        f"*{symbol}* — ${_fmt(price)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*Signal:* {signal}\n"
        f"*Confidence:* {confidence}%\n"
        f"*Regime:* {regime}\n"
        f"*Risk:* {risk}\n"
        f"*Agreement:* {agreement}\n"
        f"*Models:* {models}\n"
        f"*Timeframes:*{tf_lines}\n"
        f"*Stop:* ${sl} | *Take:* ${tp}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"_{reasoning}_"
    )


def _get_balance(market_type: str) -> float:
    try:
        if market_type == "crypto":
            return BinanceTestnetExchange().get_balance("USDT")
        return AlpacaPaperExchange().get_balance()
    except Exception:
        return 0.0
