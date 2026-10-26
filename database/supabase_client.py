import random
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, logger

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("SUPABASE_URL or SUPABASE_KEY is missing in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Table Names
TABLE_CHANNELS = "autoposterbot_db"
TABLE_SETTINGS = "autoposterbot_settings"
TABLE_VIDEOS = "viralhub_db"


# -------------------------------------------------------------
# 1. CHANNEL MANAGEMENT (autoposterbot_db)
# -------------------------------------------------------------

def get_all_channels() -> List[Dict[str, Any]]:
    """Fetches all registered channels from autoposterbot_db."""
    if not supabase:
        return []
    try:
        res = (
            supabase.table(TABLE_CHANNELS)
            .select("*")
            .order("created_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"[Database] Error fetching channels: {e}")
        return []


def get_channel(chat_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a single channel by chat_id."""
    if not supabase:
        return None
    try:
        res = (
            supabase.table(TABLE_CHANNELS)
            .select("*")
            .eq("chat_id", chat_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception as e:
        logger.error(f"[Database] Error fetching channel {chat_id}: {e}")
        return None


def add_channel(chat_id: int, channel_name: str, channel_username: Optional[str] = None) -> Dict[str, Any]:
    """Adds a new channel or activates an existing one."""
    if not supabase:
        raise ValueError("Supabase client is not initialized")

    record_id = f"channel_{abs(chat_id)}"
    payload = {
        "id": record_id,
        "chat_id": chat_id,
        "channel_name": channel_name or f"Channel {chat_id}",
        "channel_username": channel_username,
        "status": "active",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        existing = get_channel(chat_id)
        if existing:
            # Re-activate if was paused or update title
            res = (
                supabase.table(TABLE_CHANNELS)
                .update({
                    "channel_name": channel_name or existing.get("channel_name"),
                    "status": "active",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("chat_id", chat_id)
                .execute()
            )
            return res.data[0] if res.data else existing

        payload["total_posts"] = 0
        payload["success_count"] = 0
        payload["failed_count"] = 0
        payload["posted_ids"] = []
        payload["created_at"] = datetime.now(timezone.utc).isoformat()

        res = supabase.table(TABLE_CHANNELS).insert(payload).execute()
        return res.data[0] if res.data else payload
    except Exception as e:
        logger.error(f"[Database] Failed to add channel {chat_id}: {e}")
        raise e


def remove_channel(chat_id: int) -> bool:
    """Removes a channel permanently from autoposterbot_db."""
    if not supabase:
        return False
    try:
        res = supabase.table(TABLE_CHANNELS).delete().eq("chat_id", chat_id).execute()
        return bool(res.data)
    except Exception as e:
        logger.error(f"[Database] Failed to remove channel {chat_id}: {e}")
        return False


def toggle_channel_status(chat_id: int, status: str) -> bool:
    """Toggles channel status between 'active' and 'paused'."""
    if not supabase:
        return False
    try:
        res = (
            supabase.table(TABLE_CHANNELS)
            .update({
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("chat_id", chat_id)
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.error(f"[Database] Failed to toggle channel {chat_id} to {status}: {e}")
        return False


def update_channel_stats(
    chat_id: int,
    post_id: str,
    title: str,
    url: str,
    success: bool = True,
    error_msg: Optional[str] = None,
) -> bool:
    """Updates total post counts, last post timestamp/title, and appends post_id to posted_ids list."""
    if not supabase:
        return False
    try:
        channel = get_channel(chat_id)
        if not channel:
            return False

        posted_ids = channel.get("posted_ids") or []
        if post_id and post_id not in posted_ids:
            posted_ids.append(post_id)

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {
            "total_posts": (channel.get("total_posts") or 0) + (1 if success else 0),
            "success_count": (channel.get("success_count") or 0) + (1 if success else 0),
            "failed_count": (channel.get("failed_count") or 0) + (0 if success else 1),
            "updated_at": now_iso,
        }

        if success:
            update_data["last_post_id"] = str(post_id)
            update_data["last_post_title"] = title
            update_data["last_post_url"] = url
            update_data["last_post_at"] = now_iso
            update_data["posted_ids"] = posted_ids
            update_data["last_error"] = None
        else:
            update_data["last_error"] = str(error_msg or "Unknown error")

        res = supabase.table(TABLE_CHANNELS).update(update_data).eq("chat_id", chat_id).execute()
        return bool(res.data)
    except Exception as e:
        logger.error(f"[Database] Failed to update stats for channel {chat_id}: {e}")
        return False


def reset_channel_posted_ids(chat_id: int) -> bool:
    """Resets the history of posted_ids when all videos have been posted to this channel."""
    if not supabase:
        return False
    try:
        res = (
            supabase.table(TABLE_CHANNELS)
            .update({
                "posted_ids": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("chat_id", chat_id)
            .execute()
        )
        logger.info(f"[Database] Reset posted_ids history for channel {chat_id}")
        return bool(res.data)
    except Exception as e:
        logger.error(f"[Database] Failed to reset posted_ids for channel {chat_id}: {e}")
        return False


# -------------------------------------------------------------
# 2. BOT SETTINGS & STATE (autoposterbot_settings)
# -------------------------------------------------------------

def get_bot_settings() -> Dict[str, Any]:
    """Retrieves global bot settings from autoposterbot_settings."""
    default_settings = {
        "id": "global_settings",
        "is_running": True,
        "posts_per_hour": 1,
        "custom_text": "",
        "streaming_url": "",
    }
    if not supabase:
        return default_settings
    try:
        res = (
            supabase.table(TABLE_SETTINGS)
            .select("*")
            .eq("id", "global_settings")
            .maybe_single()
            .execute()
        )
        if res.data:
            return res.data
        # If not present yet, create default row
        supabase.table(TABLE_SETTINGS).insert(default_settings).execute()
        return default_settings
    except Exception as e:
        logger.error(f"[Database] Error reading bot settings: {e}")
        return default_settings


def update_bot_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates bot configuration (e.g. is_running, posts_per_hour, custom_text)."""
    if not supabase:
        return updates
    try:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        res = (
            supabase.table(TABLE_SETTINGS)
            .upsert({"id": "global_settings", **updates})
            .execute()
        )
        return res.data[0] if res.data else updates
    except Exception as e:
        logger.error(f"[Database] Error updating bot settings: {e}")
        return updates


# -------------------------------------------------------------
# 3. VIDEO SELECTION FROM viralhub_db
# -------------------------------------------------------------

def get_random_video_for_channel(posted_ids: List[str]) -> Optional[Dict[str, Any]]:
    """
    Selects a random video from Supabase viralhub_db that has NOT yet been posted
    to the target channel. If all fetched videos are exhausted, resets history.
    """
    if not supabase:
        return None

    try:
        # Sample recent batch of videos from viralhub_db
        res = (
            supabase.table(TABLE_VIDEOS)
            .select("id, slug, title, thumbnail_url, domain, duration, post_url, 720p_link, 480p_link")
            .order("scraped_at", desc=True)
            .limit(300)
            .execute()
        )
        all_videos = res.data or []
        if not all_videos:
            logger.warning("[Database] No videos found in viralhub_db table!")
            return None

        posted_set = set(str(pid) for pid in (posted_ids or []))
        available = [v for v in all_videos if str(v.get("id")) not in posted_set]

        if not available:
            logger.info("[Database] All sampled videos already posted. Cycling back through catalog.")
            return random.choice(all_videos)

        return random.choice(available)
    except Exception as e:
        logger.error(f"[Database] Error picking video from viralhub_db: {e}")
        return None
