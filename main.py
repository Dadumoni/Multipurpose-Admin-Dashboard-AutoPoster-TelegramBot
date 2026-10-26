import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import PORT, HOST, TELEGRAM_BOT_TOKEN, logger
from bot.bot_app import build_bot_application, get_bot_instance
from services.scheduler import start_scheduler, stop_scheduler
from api.routes import router as api_router

bot_polling_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_polling_task
    logger.info("==================================================")
    logger.info("Starting Telegram AutoPoster Bot & FastAPI Service")
    logger.info("==================================================")

    # 1. Initialize Telegram Bot
    bot_app = build_bot_application()

    # 2. Start Bot Polling in background asyncio task
    if bot_app:
        try:
            await bot_app.initialize()
            await bot_app.start()
            bot = bot_app.bot
            bot_info = await bot.get_me()
            logger.info(f"[Bot] Connected to Telegram as @{bot_info.username} ({bot_info.first_name})")

            # Start updater polling
            await bot_app.updater.start_polling()
            logger.info("[Bot] Telegram Long-Polling started.")

            # 3. Start Scheduler
            start_scheduler(bot)
        except Exception as e:
            logger.error(f"[Bot] Failed to start Telegram bot polling: {e}")
    else:
        logger.warning("[Bot] Bot polling skipped (TELEGRAM_BOT_TOKEN not provided).")

    yield

    # Shutdown sequence
    logger.info("Shutting down AutoPoster Bot service...")
    stop_scheduler()

    if bot_app and bot_app.updater and bot_app.updater.running:
        try:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
            logger.info("[Bot] Telegram polling stopped cleanly.")
        except Exception as e:
            logger.warning(f"[Bot] Error during shutdown: {e}")


app = FastAPI(
    title="Telegram AutoPoster Bot Service",
    description="Automated Telegram Multi-Channel Video Broadcaster with Supabase & Render Support",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for Admin Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API Router
app.include_router(api_router)


if __name__ == "__main__":
    logger.info(f"Starting server on {HOST}:{PORT}...")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
