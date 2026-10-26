from typing import Optional
from telegram.ext import Application, ApplicationBuilder
from config import TELEGRAM_BOT_TOKEN, logger
from bot.handlers import register_bot_handlers

_app_instance: Optional[Application] = None


def build_bot_application() -> Optional[Application]:
    """Creates and configures the telegram.ext Application instance."""
    global _app_instance

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[BotApp] TELEGRAM_BOT_TOKEN is empty. Bot polling cannot start.")
        return None

    if _app_instance:
        return _app_instance

    logger.info("[BotApp] Building python-telegram-bot Application...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    register_bot_handlers(app)
    _app_instance = app
    return app


def get_bot_instance():
    """Returns the current telegram.ext Application or bot instance."""
    return _app_instance.bot if _app_instance else None
