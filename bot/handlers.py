from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
import logging

from agents.ensemble_analyzer import EnsembleAnalyzer
from agents.risk_manager import RiskManager
from agents.signal_logger import log_signal, log_trade, get_stats
from agents.auto_trader import auto_trader
from agents.scanner import scanner
from data.market_data import get_multi_timeframe_data
from exchanges.crypto import get_crypto_exchange
from exchanges.paper import PaperExchange
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
    "/scan — Scan top crypto for signals\n"
    "/autotrade — Auto-trade mode status\n"
    "/autotrade on [confidence] — Enable auto-trade\n"
    "/autotrade off — Disable auto-trade\n"
    "/portfolio — View open positions\n"
    "/balance — Check balances\n"
    "/performance — P&L and trade stats\n"
    "/stats — Signal history\n"
    "/reset — Reset paper wallet to $10,000\n"
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
        "- Auto-trade mode (autonomous execution)\n"
        "- Market scanner\n"
        "- Signal & performance tracking\n\n"
        f"{HELP_TEXT}"
    )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def _do_trade(symbol: str, auto: bool = False) -> str:
    market = _detect_market(symbol)
    multi_data = get_multi_timeframe_data(symbol, market)
    if not multi_data:
        return f"No data available for {symbol}"

    result = await analyzer.analyze_all(symbol, market, multi_data)
    signal = result.get("signal", "HOLD")

    price = 0
    for tf_data in multi_data.values():
        if tf_data is not None and not tf_data.empty:
            price = tf_data["close"].iloc[-1]
            break

    text = _format_ensemble(symbol, result, price)
    log_signal(symbol, signal, result.get("confidence", 0), result.get("regime", "?"),
               result.get("risk", "?"), price, result.get("agreement", "?"),
               result.get("models_used", 0), result.get("reasoning", ""))

    if signal == "HOLD":
        return text + "\n\nNo actionable signal."

    balance = _get_balance(market)
    approved, reason = risk_manager.check_trade(
        signal=signal,
        confidence=result.get("confidence", 0),
        risk=result.get("risk", "MEDIUM"),
        balance=balance,
        current_price=price,
        suggested_stop=result.get("stop_loss"),
        atr=result.get("atr"),
        regime=result.get("regime"),
    )

    if not approved:
        return text + f"\n\nRisk check: {reason}"

    quantity = risk_manager.calculate_size(balance, price, result.get("atr"), result.get("regime"))
    side = "buy" if signal == "BUY" else "sell"

    if auto:
        ex = get_crypto_exchange() if market == "crypto" else AlpacaPaperExchange()
        if market == "crypto" and not isinstance(ex, PaperExchange):
            return text + f"\n\nAuto-trade requires paper exchange."
        try:
            order = ex.market_order(symbol, side, quantity)
            log_trade(symbol, side, quantity, order.price or price, order.status,
                      signal, result.get("confidence", 0), order_id=order.order_id)
            auto_trader.record_trade()
            return text + f"\n\nAuto-executed: {side.upper()} {quantity:.4f} @ ${order.price or price:.2f} (ID: {order.order_id})"
        except Exception as e:
            return text + f"\n\nAuto-execution failed: {e}"

    text += f"\n\nProposed: {side.upper()} {quantity:.4f} ({symbol}) ~${quantity * price:.2f}"
    text += f"\n/confirm {side} {symbol} {quantity:.4f} {result.get('confidence',0)}"
    return text


async def analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /analyze <symbol>\nExample: /analyze BTC or /analyze AAPL")
        return
    symbol = _normalize_symbol(ctx.args[0])
    msg = await update.message.reply_text(f"Analyzing {symbol}...")
    try:
        text = await _do_trade(symbol)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"analyze error", exc_info=True)
        await msg.edit_text(f"Error: {type(e).__name__}: {e}")


async def trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /trade <symbol>\nExample: /trade BTC")
        return
    symbol = _normalize_symbol(ctx.args[0])
    msg = await update.message.reply_text(f"Analyzing {symbol} for trade...")
    try:
        if auto_trader.enabled and auto_trader.can_trade()[0]:
            text = await _do_trade(symbol, auto=True)
        else:
            text = await _do_trade(symbol, auto=False)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"trade error", exc_info=True)
        await msg.edit_text(f"Error: {type(e).__name__}: {e}")


async def confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or len(ctx.args) < 4:
        await update.message.reply_text("Usage: /confirm <side> <symbol> <quantity> <confidence>")
        return
    side, symbol, qty_str, conf_str = ctx.args[0], _normalize_symbol(ctx.args[1]), ctx.args[2], ctx.args[3]
    quantity, confidence = float(qty_str), int(conf_str)
    market = _detect_market(symbol)
    try:
        ex = get_crypto_exchange() if market == "crypto" else AlpacaPaperExchange()
        order = ex.market_order(symbol, side, quantity)
        log_trade(symbol, side, quantity, order.price or 0, order.status,
                  "MANUAL", confidence, order_id=order.order_id)
        await update.message.reply_text(
            f"Executed {side.upper()} {quantity:.4f} {symbol} @ ${order.price or 0:.2f} (ID: {order.order_id})"
        )
    except Exception as e:
        log_trade(symbol, side, quantity, 0, "failed", "MANUAL", confidence, error=str(e))
        await update.message.reply_text(f"Order failed: {e}")


async def portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Open Positions:\n"]
    try:
        for pos in AlpacaPaperExchange().get_all_positions():
            lines.append(f"{pos.symbol}: {pos.quantity:.2f} @ ${pos.current_price:.2f} ({pos.unrealized_pnl_pct:+.2f}%)")
    except Exception as e:
        logger.error(f"Alpaca positions error: {e}")
    try:
        ex = get_crypto_exchange()
        if isinstance(ex, PaperExchange):
            for pos in ex.get_all_positions():
                lines.append(f"{pos.symbol}: {pos.quantity:.6f} @ ${pos.current_price:.2f} ({pos.unrealized_pnl_pct:+.2f}%)")
    except Exception as e:
        logger.error(f"Crypto positions error: {e}")
    if len(lines) == 1:
        lines.append("No open positions.")
    await update.message.reply_text("\n".join(lines))


async def balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Account Balances:\n"]
    try:
        lines.append(f"Alpaca (Stocks): ${AlpacaPaperExchange().get_balance():.2f}")
    except Exception as e:
        logger.error(f"Alpaca balance error: {e}")
        lines.append("Alpaca: not configured")
    try:
        ex = get_crypto_exchange()
        bal = ex.get_balance("USDT")
        if isinstance(ex, PaperExchange):
            lines.append(f"Paper Wallet: ${bal:.2f}")
        elif isinstance(ex, BybitTestnetExchange):
            lines.append(f"Bybit Testnet: ${bal:.2f}")
        else:
            lines.append(f"Binance Testnet: ${bal:.2f}")
    except Exception as e:
        logger.error(f"Crypto exchange balance error: {e}")
        lines.append("Crypto exchange: not configured")
    await update.message.reply_text("\n".join(lines))


async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_stats())


async def reset_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ex = get_crypto_exchange()
    if isinstance(ex, PaperExchange):
        ex.reset()
        await update.message.reply_text("Paper wallet reset to $10,000. All positions cleared.")
    else:
        await update.message.reply_text("Reset only available for paper exchange.")


async def autotrade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(auto_trader.status())
        return
    cmd = ctx.args[0].lower()
    if cmd == "on":
        threshold = int(ctx.args[1]) if len(ctx.args) > 1 else 75
        auto_trader.enable(threshold=threshold)
        await update.message.reply_text(
            f"Auto-trade enabled (min confidence: {threshold}%, daily limit: {auto_trader.max_daily_trades})"
        )
    elif cmd == "off":
        auto_trader.disable()
        await update.message.reply_text("Auto-trade disabled.")
    else:
        await update.message.reply_text(auto_trader.status())


async def scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Scanning top crypto for signals...")
    try:
        results = await scanner.scan()
        if not results:
            await msg.edit_text("No results.")
            return

        lines = ["Market Scan:\n"]
        for r in results:
            sig = r["signal"]
            icon = {"BUY": "▲", "SELL": "▼", "HOLD": "―"}.get(sig, "?")
            sym = r["symbol"]
            conf = r["confidence"]
            regime = r["regime"]
            price = _fmt(r["price"])
            lines.append(f"{icon} *{sym}* — {sig} ({conf}%) | ${price} | {regime}")

        lines.append(f"\nScanned {len(results)} symbols")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"scan error", exc_info=True)
        await msg.edit_text(f"Scan failed: {e}")


async def performance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ex = get_crypto_exchange()
    if not isinstance(ex, PaperExchange):
        await update.message.reply_text("Performance only available for paper exchange.")
        return

    balance = ex.get_balance("USDT")
    holdings = ex.holdings
    trades = ex.trades
    n_trades = len(trades)

    lines = ["Performance:\n"]
    lines.append(f"Total value: ${balance:.2f}")
    if holdings:
        for asset, qty in holdings.items():
            pos = ex.get_position(f"{asset}/USDT")
            if pos:
                lines.append(f"{asset}: {qty:.6f} ({pos.unrealized_pnl_pct:+.2f}%)")

    if n_trades > 0:
        buys = [t for t in trades if t["side"] == "buy"]
        sells = [t for t in trades if t["side"] == "sell"]
        total_bought = sum(t["cost"] for t in buys)
        total_sold = sum(t["cost"] for t in sells)
        realized_pnl = total_sold - total_bought
        lines.append(f"Trades: {n_trades} ({len(buys)} buys, {len(sells)} sells)")
        lines.append(f"Realized P&L: ${realized_pnl:+.2f}")

        if n_trades >= 2:
            costs = [t["cost"] for t in trades if t["cost"] > 0]
            avg_trade = sum(costs) / len(costs) if costs else 0
            lines.append(f"Avg trade size: ${avg_trade:.2f}")
    else:
        lines.append("No trades yet.")

    await update.message.reply_text("\n".join(lines))


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
        f"-----------------------\n"
        f"*Signal:* {signal}\n"
        f"*Confidence:* {confidence}%\n"
        f"*Regime:* {regime}\n"
        f"*Risk:* {risk}\n"
        f"*Agreement:* {agreement}\n"
        f"*Models:* {models}\n"
        f"*Timeframes:*{tf_lines}\n"
        f"*Stop:* ${sl} | *Take:* ${tp}\n"
        f"-----------------------\n"
        f"_{reasoning}_"
    )


def _get_balance(market_type: str) -> float:
    try:
        if market_type == "crypto":
            return get_crypto_exchange().get_balance("USDT")
        return AlpacaPaperExchange().get_balance()
    except Exception:
        return 0.0
