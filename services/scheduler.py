import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import logger
from database.supabase_client import (
    get_all_channels,
    get_bot_settings,
)
from services.poster import post_video_to_channel

scheduler = AsyncIOScheduler()
_current_bot = None
JOB_ID = "automated_hourly_posting"


async def hourly_posting_job(bot=None):
    """
    Scheduled job running at defined intervals for all active channels sequentially.
    """
    active_bot = bot or _current_bot
    if not active_bot:
        logger.warning("[Scheduler] No bot instance registered for automated posting.")
        return

    settings = get_bot_settings()
    if not settings.get("is_running", True):
        logger.info("[Scheduler] Automated posting skipped because bot is paused/stopped.")
        return

    channels = get_all_channels()
    active_channels = [c for c in channels if c.get("status") == "active"]

    if not active_channels:
        logger.info("[Scheduler] No active channels found in autoposterbot_db.")
        return

    logger.info(f"[Scheduler] Running automated post for {len(active_channels)} channel(s)...")

    for ch in active_channels:
        # Check if stopped mid-loop
        current_settings = get_bot_settings()
        if not current_settings.get("is_running", True):
            logger.info("[Scheduler] Posting aborted because bot was stopped.")
            break

        chat_id = ch["chat_id"]
        logger.info(f"[Scheduler] Posting to channel '{ch.get('channel_name')}' (ID: {chat_id})")
        await post_video_to_channel(active_bot, chat_id)
        # 5 second delay between channels to avoid rate limits
        await asyncio.sleep(5)


async def process_initial_burst(bot, chat_id: int):
    """
    Immediately broadcasts 10 video posts with a 10-second gap
    when a new channel is registered.
    """
    logger.info(f"[InitialBurst] Starting 10 initial posts burst for channel {chat_id}")
    for i in range(10):
        settings = get_bot_settings()
        if not settings.get("is_running", True):
            logger.info("[InitialBurst] Posting cancelled because bot was paused.")
            break

        await post_video_to_channel(bot, chat_id)
        if i < 9:
            await asyncio.sleep(10)

    logger.info(f"[InitialBurst] Completed 10 initial posts burst for channel {chat_id}")


def update_scheduler_interval(posts_per_hour: int):
    """
    Dynamically reschedules the automated posting job based on posts_per_hour setting.
    e.g. 1 post/hr -> 60 minutes
         2 posts/hr -> 30 minutes
         4 posts/hr -> 15 minutes
    """
    posts_per_hour = max(1, min(60, int(posts_per_hour or 1)))
    interval_minutes = max(1, 60 // posts_per_hour)

    try:
        if scheduler.get_job(JOB_ID):
            scheduler.reschedule_job(
                JOB_ID,
                trigger=IntervalTrigger(minutes=interval_minutes),
            )
            logger.info(f"[Scheduler] Rescheduled automated posting: every {interval_minutes}m ({posts_per_hour} post(s)/hr)")
        else:
            scheduler.add_job(
                hourly_posting_job,
                IntervalTrigger(minutes=interval_minutes),
                id=JOB_ID,
                replace_existing=True,
            )
            logger.info(f"[Scheduler] Added automated posting job: every {interval_minutes}m")
    except Exception as e:
        logger.error(f"[Scheduler] Failed to update scheduler interval: {e}")


def start_scheduler(bot):
    """Starts the background scheduler with current database settings."""
    global _current_bot
    _current_bot = bot

    settings = get_bot_settings()
    posts_per_hour = settings.get("posts_per_hour", 1)

    update_scheduler_interval(posts_per_hour)

    if not scheduler.running:
        scheduler.start()
        logger.info("[Scheduler] Automated posting scheduler started successfully.")


def stop_scheduler():
    """Shuts down the background scheduler cleanly."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Automated posting scheduler stopped.")
