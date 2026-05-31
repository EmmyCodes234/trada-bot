import sys
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import settings
from bot.handlers import start, help_cmd, analyze, trade, button_callback, portfolio, balance, stats


def main():
    if not settings.telegram_bot_token or settings.telegram_bot_token == "your_telegram_bot_token_here":
        print("ERROR: TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and add your token.")
        sys.exit(1)

    if not settings.openmodel_api_key or settings.openmodel_api_key == "your_openmodel_api_key_here":
        print("ERROR: OPENMODEL_API_KEY not set.")
        sys.exit(1)

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("trade", trade))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Trada bot running...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
