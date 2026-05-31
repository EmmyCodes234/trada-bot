from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Optional

from agents.market_analyzer import MarketAnalyzer
from agents.risk_manager import RiskManager
from data.market_data import get_stock_data, get_crypto_data, summarize_data
from exchanges.crypto import BinanceTestnetExchange
from exchanges.stocks import AlpacaPaperExchange
from config import settings

analyzer = MarketAnalyzer()
risk_manager = RiskManager()

HELP_TEXT = (
    "/start — Show this menu\n"
    "/analyze <symbol> — AI analysis (no trade)\n"
    "/trade <symbol> — AI analysis + execute if signal\n"
    "/portfolio — View open positions\n"
    "/balance — Check account balance\n"
    "/help — Show commands"
)


CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "DOT", "AVAX", "LINK", "MATIC", "UNI", "ATOM", "LTC", "BCH", "TRX"}

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


def _format_num(n: Optional[float], decimals: int = 4) -> str:
    if n is None:
        return "N/A"
    return f"{n:.{decimals}f}"


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Trada — AI Trading Agent\n"
        "Powered by OpenModel.ai\n\n"
        f"{HELP_TEXT}"
    )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /analyze <symbol>\nExample: /analyze BTC/USDT or /analyze AAPL")
        return

    symbol = _normalize_symbol(ctx.args[0])
    market_type = _detect_market(symbol)
    msg = await update.message.reply_text(f"Analyzing {symbol}...")

    try:
        if market_type == "crypto":
            df = get_crypto_data(symbol, interval="1d", limit=60)
        else:
            df = get_stock_data(symbol, interval="1d", period="2mo")

        data = summarize_data(df)
        if not data:
            await msg.edit_text(f"No data available for {symbol} from any source")
            return

        analysis = await analyzer.analyze(symbol, market_type, data)
        if not analysis:
            await msg.edit_text(f"AI analysis failed for {symbol}. Check Railway logs for details.")
            return

        text = _format_analysis(symbol, analysis, data)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"analyze error", exc_info=True)
        await msg.edit_text(f"Error: {type(e).__name__}: {e}")


async def trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /trade <symbol>\nExample: /trade BTC/USDT")
        return

    symbol = _normalize_symbol(ctx.args[0])
    market_type = _detect_market(symbol)
    msg = await update.message.reply_text(f"Analyzing {symbol} for trade...")

    try:
        if market_type == "crypto":
            df = get_crypto_data(symbol, interval="1d", limit=60)
        else:
            df = get_stock_data(symbol, interval="1d", period="2mo")

        data = summarize_data(df)
        if not data:
            await msg.edit_text(f"No data available for {symbol}")
            return

        analysis = await analyzer.analyze(symbol, market_type, data)
        if not analysis:
            await msg.edit_text(f"Analysis failed for {symbol}. Check Railway logs for details.")
            return

        signal = analysis.get("signal", "HOLD")
        if signal == "HOLD":
            text = _format_analysis(symbol, analysis, data)
            text += "\n\nNo actionable signal."
            await msg.edit_text(text, parse_mode="Markdown")
            return

        balance = _get_balance(market_type)
        current_price = data.get("current_price", 0)
        approved, reason = risk_manager.check_trade(
            signal=signal,
            confidence=analysis.get("confidence", 0),
            risk=analysis.get("risk", "MEDIUM"),
            balance=balance,
            current_price=current_price,
            suggested_stop=analysis.get("stop_loss"),
        )

        text = _format_analysis(symbol, analysis, data)
        if not approved:
            text += f"\n\nRisk check failed: {reason}"
            await msg.edit_text(text, parse_mode="Markdown")
            return

        max_pos = balance * (settings.max_position_size_pct / 100)
        quantity = max_pos / current_price if current_price > 0 else 0
        side = "buy" if signal == "BUY" else "sell"

        text += f"\n\nProposed: {side.upper()} {quantity:.4f} {symbol.split('/')[0] if market_type == 'crypto' else symbol} (~${max_pos:.2f})"

        keyboard = [[
            InlineKeyboardButton("Execute", callback_data=f"exec|{market_type}|{symbol}|{side}|{quantity}"),
            InlineKeyboardButton("Cancel", callback_data="cancel"),
        ]]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"trade error", exc_info=True)
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
        _, market_type, symbol, side, quantity = parts
        quantity = float(quantity)
        try:
            if market_type == "crypto":
                ex = BinanceTestnetExchange()
            else:
                ex = AlpacaPaperExchange()

            if side == "buy":
                ex.market_order(symbol, "buy", quantity)
            else:
                ex.market_order(symbol, "sell", quantity)

            await query.edit_message_text(f"Executed {side.upper()} {quantity:.4f} {symbol}")
        except Exception as e:
            await query.edit_message_text(f"Order failed: {e}")


async def portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Open Positions:\n"]
    try:
        for pos in AlpacaPaperExchange().get_all_positions():
            lines.append(
                f"{pos.symbol}: {pos.quantity:.2f} @ ${pos.current_price:.2f} "
                f"({pos.unrealized_pnl_pct:+.2f}%)"
            )
        if len(lines) == 1:
            lines.append("No open positions.")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["Account Balances:\n"]
    try:
        alpaca_bal = AlpacaPaperExchange().get_balance()
        lines.append(f"Alpaca (Stocks): ${alpaca_bal:.2f}")
    except Exception:
        lines.append("Alpaca: not configured")

    try:
        binance_bal = BinanceTestnetExchange().get_balance("USDT")
        lines.append(f"Binance Testnet: ${binance_bal:.2f}")
    except Exception:
        lines.append("Binance: not configured")

    await update.message.reply_text("\n".join(lines))


def _format_analysis(symbol: str, analysis: dict, data: dict) -> str:
    signal = analysis.get("signal", "N/A")
    confidence = analysis.get("confidence", "N/A")
    risk = analysis.get("risk", "N/A")
    reasoning = analysis.get("reasoning", "N/A")
    entry = _format_num(analysis.get("suggested_entry"))
    sl = _format_num(analysis.get("stop_loss"))
    tp = _format_num(analysis.get("take_profit"))

    signal_icon = {"BUY": "BUY", "SELL": "SELL", "HOLD": "HOLD"}.get(signal, signal)

    lines = [
        f"*{symbol}* — {signal_icon}",
        f"Price: ${_format_num(data.get('current_price'))}",
        f"Change: {data.get('change_pct', 'N/A')}%",
        "",
        f"Signal: {signal}",
        f"Confidence: {confidence}%",
        f"Risk: {risk}",
        f"Reasoning: {reasoning}",
        f"Entry: ${entry}",
        f"Stop: ${sl}",
        f"Take: ${tp}",
    ]
    return "\n".join(lines)


def _get_balance(market_type: str) -> float:
    try:
        if market_type == "crypto":
            return BinanceTestnetExchange().get_balance("USDT")
        return AlpacaPaperExchange().get_balance()
    except Exception:
        return 0.0
