import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from config import logger
from bot.bot_app import get_bot_instance
from database.supabase_client import (
    get_all_channels,
    get_channel,
    add_channel,
    remove_channel,
    toggle_channel_status,
    get_bot_settings,
    update_bot_settings,
)
from services.poster import post_video_to_channel
from services.scheduler import (
    update_scheduler_interval,
    process_initial_burst,
    hourly_posting_job,
)

router = APIRouter()


# -------------------------------------------------------------
# PYDANTIC REQUEST MODELS
# -------------------------------------------------------------
class AddChannelRequest(BaseModel):
    chat_id: int
    channel_name: Optional[str] = None
    channel_username: Optional[str] = None


class ToggleChannelRequest(BaseModel):
    status: Optional[str] = "active"  # "active" or "paused"
    is_active: Optional[bool] = None


class CustomTextRequest(BaseModel):
    text: str


class HourlyRateRequest(BaseModel):
    posts_per_hour: Optional[int] = None
    hourlyPostsPerChannel: Optional[int] = None


class PostNowRequest(BaseModel):
    chat_id: Optional[int] = None


# -------------------------------------------------------------
# HEALTH CHECKS (Render requires a 200 OK HTTP response)
# -------------------------------------------------------------
@router.get("/")
@router.get("/health")
async def health_check():
    bot = get_bot_instance()
    settings = get_bot_settings()
    channels = get_all_channels()

    return {
        "status": "healthy",
        "service": "AutoPoster Telegram Bot API",
        "bot_initialized": bot is not None,
        "is_running": settings.get("is_running", True),
        "total_channels": len(channels),
    }


# -------------------------------------------------------------
# BOT STATUS FOR ADMIN DASHBOARD
# -------------------------------------------------------------
@router.get("/api/status")
async def get_bot_status():
    bot = get_bot_instance()
    settings = get_bot_settings()
    channels = get_all_channels()

    bot_username = ""
    bot_name = "Poster Bot"
    if bot:
        try:
            me = await bot.get_me()
            bot_username = me.username or ""
            bot_name = me.first_name or "Poster Bot"
        except Exception:
            pass

    is_running = settings.get("is_running", True)
    hourly_rate = settings.get("posts_per_hour", 1)

    return {
        "success": True,
        "online": bot is not None,
        "state": {
            "id": "status",
            "is_running": is_running,
            "stopped": not is_running,
            "bot_name": bot_name,
            "bot_username": bot_username,
            "last_started_at": settings.get("last_run_at"),
            "database": "viralhub_db",
        },
        "channels": channels,
        "totalChannels": len(channels),
        "customText": settings.get("custom_text", ""),
        "hourlyPostsPerChannel": hourly_rate,
    }


# -------------------------------------------------------------
# BOT START / STOP CONTROL
# -------------------------------------------------------------
@router.post("/api/control/start")
@router.post("/api/telegram-bot/start")
async def start_bot_control():
    update_bot_settings({"is_running": True})
    logger.info("[Control] Automated posting started/resumed via API.")
    return {
        "success": True,
        "message": "Automated Telegram Bot posting resumed.",
        "is_running": True,
    }


@router.post("/api/control/stop")
@router.post("/api/telegram-bot/stop")
async def stop_bot_control():
    update_bot_settings({"is_running": False})
    logger.info("[Control] Automated posting paused via API.")
    return {
        "success": True,
        "message": "Automated Telegram Bot posting paused.",
        "is_running": False,
    }


# -------------------------------------------------------------
# TRIGGER POST NOW (Test post / Immediate Broadcast)
# -------------------------------------------------------------
@router.post("/api/control/post-now")
@router.post("/api/telegram-bot/test-post")
async def trigger_post_now(payload: Optional[PostNowRequest] = None):
    bot = get_bot_instance()
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram bot is not initialized")

    chat_id = payload.chat_id if payload else None

    if chat_id:
        res = await post_video_to_channel(bot, chat_id)
        return res

    # Otherwise broadcast to all active channels
    channels = get_all_channels()
    active = [c for c in channels if c.get("status") == "active"]
    if not active:
        return {"success": False, "message": "No active channels registered."}

    results = []
    for ch in active:
        res = await post_video_to_channel(bot, ch["chat_id"])
        results.append(res)
        await asyncio.sleep(2)

    return {
        "success": True,
        "total_dispatched": len(results),
        "results": results,
    }


# -------------------------------------------------------------
# CHANNEL ENDPOINTS FOR DASHBOARD
# -------------------------------------------------------------
@router.get("/api/channels")
@router.get("/api/telegram-bot/channels")
async def list_channels():
    channels = get_all_channels()
    return {"success": True, "channels": channels, "total": len(channels)}


@router.post("/api/channels")
@router.post("/api/telegram-bot/channels")
async def add_new_channel(body: AddChannelRequest, background_tasks: BackgroundTasks):
    bot = get_bot_instance()
    chat_id = body.chat_id
    channel_name = body.channel_name

    # Try resolving title from Telegram if not passed
    if bot and not channel_name:
        try:
            chat_info = await bot.get_chat(chat_id)
            channel_name = chat_info.title or str(chat_id)
            if not body.channel_username:
                body.channel_username = chat_info.username
        except Exception as e:
            logger.warning(f"Could not verify chat with Telegram: {e}")

    try:
        channel = add_channel(chat_id, channel_name or str(chat_id), body.channel_username)
        # Dispatch 10 initial posts in background
        if bot:
            background_tasks.add_task(process_initial_burst, bot, chat_id)

        return {
            "success": True,
            "message": f"Channel '{channel.get('channel_name')}' registered. Initial 10-post burst queued.",
            "channel": channel,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/channels/{chat_id}/toggle")
@router.post("/api/telegram-bot/channels/{chat_id}/toggle")
async def toggle_channel(chat_id: int, body: ToggleChannelRequest):
    status = body.status
    if body.is_active is not None:
        status = "active" if body.is_active else "paused"

    success = toggle_channel_status(chat_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found")

    return {"success": True, "chat_id": chat_id, "status": status}


@router.delete("/api/channels/{chat_id}")
@router.delete("/api/telegram-bot/channels/{chat_id}")
async def delete_channel(chat_id: int):
    success = remove_channel(chat_id)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found or already deleted")
    return {"success": True, "message": f"Channel {chat_id} deleted."}


@router.post("/api/channels/{chat_id}/test-post")
@router.post("/api/telegram-bot/channels/{chat_id}/test-post")
async def test_post_single_channel(chat_id: int):
    bot = get_bot_instance()
    if not bot:
        raise HTTPException(status_code=503, detail="Telegram Bot not initialized")
    res = await post_video_to_channel(bot, chat_id)
    return res


# -------------------------------------------------------------
# SETTINGS: CUSTOM CAPTION & HOURLY RATE
# -------------------------------------------------------------
@router.get("/api/settings/custom-text")
async def get_custom_caption():
    settings = get_bot_settings()
    return {"success": True, "customText": settings.get("custom_text", "")}


@router.post("/api/settings/custom-text")
@router.post("/api/telegram-bot/settings/custom-text")
async def set_custom_caption(body: CustomTextRequest):
    update_bot_settings({"custom_text": body.text.strip()})
    return {"success": True, "customText": body.text.strip()}


@router.post("/api/settings/hourly-rate")
@router.post("/api/telegram-bot/hourly-rate")
async def set_hourly_rate(body: HourlyRateRequest):
    rate = body.posts_per_hour or body.hourlyPostsPerChannel or 1
    update_bot_settings({"posts_per_hour": rate})
    update_scheduler_interval(rate)
    return {"success": True, "posts_per_hour": rate}
