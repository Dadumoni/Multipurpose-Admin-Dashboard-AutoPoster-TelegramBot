import os
import re
import io
import requests
from typing import Optional, Dict, Any
from telegram import Bot
from config import STREAMING_URL, logger
from database.supabase_client import (
    get_channel,
    get_bot_settings,
    get_random_video_for_channel,
    update_channel_stats,
    reset_channel_posted_ids,
)


def slugify(title: str) -> str:
    """Converts title to lowercase URL-friendly slug, e.g. 'My Sample Video' -> 'my-sample-video'"""
    title = str(title or "video").lower()
    title = re.sub(r'[\s_]+', '-', title)
    title = re.sub(r'[^a-z0-9\-]', '', title)
    title = re.sub(r'\-+', '-', title)
    return title.strip('-') or "video"


def format_caption(title: str, video_link: str, custom_text: str = "") -> str:
    """
    Builds the standardized HTML caption:
    <b><code>Title</code></b>
    
    <b>Watch Full Video👇</b>
    <blockquote>video_link</blockquote>

    custom_text
    """
    formatted_title = f"<b><code>{title}</code></b>"
    formatted_heading = "<b>Watch Full Video👇</b>"
    formatted_link = f"<blockquote>{video_link}</blockquote>"

    parts = [formatted_title, formatted_heading, formatted_link]
    if custom_text and custom_text.strip():
        parts.append(custom_text.strip())

    return "\n\n".join(parts)


async def post_video_to_channel(bot: Bot, chat_id: int, post: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fetches an unposted video from Supabase viralhub_db and broadcasts it
    to the target Telegram channel with formatted thumbnail and HTML caption.
    """
    try:
        channel_data = get_channel(chat_id)
        if not channel_data:
            err = f"Channel {chat_id} not found in autoposterbot_db."
            logger.warning(err)
            return {"success": False, "error": err}

        # Check if channel is paused
        if channel_data.get("status") == "paused":
            logger.info(f"Skipping post to channel {chat_id} because it is paused.")
            return {"success": False, "error": "Channel is paused"}

        posted_ids = channel_data.get("posted_ids") or []

        # Fetch video if not provided
        if not post:
            post = get_random_video_for_channel(posted_ids)

        if not post:
            err = f"No videos available in viralhub_db for channel {chat_id}."
            logger.warning(err)
            update_channel_stats(chat_id, "", "", "", success=False, error_msg=err)
            return {"success": False, "error": err}

        post_id = str(post.get("id"))
        title = post.get("title") or "Untitled Video"
        thumbnail_url = post.get("thumbnail_url")
        slug = post.get("slug") or slugify(title)

        # Settings
        settings = get_bot_settings()
        custom_text = settings.get("custom_text", "")
        base_streaming_url = (settings.get("streaming_url") or STREAMING_URL or "").rstrip("/")
        video_link = f"{base_streaming_url}/{slug}" if base_streaming_url else f"https://viralhub.space/{slug}"

        caption = format_caption(title, video_link, custom_text)

        # Attempt to send photo thumbnail
        sent = False
        if thumbnail_url and str(thumbnail_url).startswith("http"):
            try:
                img_res = requests.get(thumbnail_url, timeout=12)
                if img_res.status_code == 200 and len(img_res.content) > 500:
                    image_bytes = io.BytesIO(img_res.content)
                    image_bytes.name = f"thumb_{post_id}.jpg"

                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=image_bytes,
                        caption=caption,
                        parse_mode="HTML",
                    )
                    sent = True
            except Exception as photo_err:
                logger.warning(f"Failed to send thumbnail to {chat_id}, falling back to message: {photo_err}")

        # Fallback to direct HTML text message
        if not sent:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )

        # Record successful post in Supabase
        update_channel_stats(
            chat_id=chat_id,
            post_id=post_id,
            title=title,
            url=video_link,
            success=True,
        )

        logger.info(f"Successfully posted video '{title[:35]}...' (ID: {post_id}) to channel {chat_id}")
        return {
            "success": True,
            "post_id": post_id,
            "title": title,
            "video_link": video_link,
            "chat_id": chat_id,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error posting video to channel {chat_id}: {error_msg}")
        update_channel_stats(chat_id, "", "", "", success=False, error_msg=error_msg)
        return {"success": False, "error": error_msg}
