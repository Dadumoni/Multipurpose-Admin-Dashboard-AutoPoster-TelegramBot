import asyncio
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from config import logger
from database.supabase_client import (
    get_all_channels,
    get_channel,
    add_channel,
    remove_channel,
    get_bot_settings,
    update_bot_settings,
)
from services.poster import post_video_to_channel
from services.scheduler import process_initial_burst

# Conversation States
WAITING_FOR_CHANNEL = 1
WAITING_FOR_CUSTOM_TEXT = 2


# -------------------------------------------------------------
# COMMAND: /start
# -------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_bot_settings()
    is_running = settings.get("is_running", True)
    rate = settings.get("posts_per_hour", 1)
    status_label = "🟢 <b>Active / Running</b>" if is_running else "🔴 <b>Stopped / Paused</b>"

    welcome_text = (
        "👋 <b>Welcome to the Automated Telegram Poster Bot!</b>\n\n"
        f"⚙️ <b>Current Status:</b> {status_label}\n"
        f"⏱️ <b>Posting Rate:</b> {rate} post(s) / hr per channel\n"
        "🗄️ <b>Database:</b> Supabase (<code>viralhub_db</code>)\n\n"
        "📌 <b>Supported Commands:</b>\n"
        "• /start - Show this welcome status and command guide.\n"
        "• /add_channel - Add a channel (triggers 10 immediate video posts).\n"
        "• /remove_channel &lt;chat_id&gt; - Remove a channel from the database.\n"
        "• /all_channel - List all connected channels and post statistics.\n"
        "• /add_custom_text - Set custom footer text/emojis/links for captions.\n"
        "• /test_post - Immediately send a video to all connected channels.\n"
        "• /stop_posting - Temporarily pause automated posting.\n"
        "• /start_posting - Resume automated posting.\n"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")


# -------------------------------------------------------------
# CONVERSATION: /add_channel
# -------------------------------------------------------------
async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ Please <b>forward a message</b> from your target channel here, "
        "or send the channel's <b>Channel ID</b> directly (e.g. <code>-1001234567890</code>).\n\n"
        "<i>Make sure this bot is added as an Administrator with 'Post Messages' rights first!</i>",
        parse_mode="HTML",
    )
    return WAITING_FOR_CHANNEL


async def receive_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = None
    chat_title = "Unknown Channel"
    chat_username = None

    # Check forward origin
    if message.forward_origin and hasattr(message.forward_origin, "chat"):
        f_chat = message.forward_origin.chat
        chat_id = f_chat.id
        chat_title = f_chat.title or str(chat_id)
        chat_username = getattr(f_chat, "username", None)

    if not chat_id and hasattr(message, "forward_from_chat") and message.forward_from_chat:
        f_chat = message.forward_from_chat
        chat_id = f_chat.id
        chat_title = f_chat.title or str(chat_id)
        chat_username = getattr(f_chat, "username", None)

    # Check manual chat ID input
    if not chat_id:
        text_input = (message.text or "").strip()
        try:
            chat_id = int(text_input)
            chat_info = await context.bot.get_chat(chat_id)
            chat_title = chat_info.title or str(chat_id)
            chat_username = chat_info.username
        except Exception:
            await message.reply_text(
                "❌ <b>Invalid Channel ID or forwarded message.</b>\n"
                "Please verify the bot is an Admin in the channel and try again, or type /cancel to abort.",
                parse_mode="HTML",
            )
            return WAITING_FOR_CHANNEL

    # Check if already added in Supabase
    existing = get_channel(chat_id)
    if existing:
        await message.reply_text(
            f"⚠️ Channel <b>{chat_title}</b> (<code>{chat_id}</code>) is already saved in <code>autoposterbot_db</code>!",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        add_channel(chat_id, chat_title, chat_username)
    except Exception as e:
        await message.reply_text(f"❌ Failed to save channel to database: {e}")
        return ConversationHandler.END

    await message.reply_text(
        f"✅ <b>Channel Added Successfully!</b>\n\n"
        f"📢 <b>Name:</b> {chat_title}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
        f"🔗 <b>Username:</b> @{chat_username if chat_username else 'None'}\n\n"
        f"🚀 <b>Starting initial burst:</b> 10 posts are being dispatched right now with a 10s gap...",
        parse_mode="HTML",
    )

    # Trigger 10 initial burst posts in background
    asyncio.create_task(process_initial_burst(context.bot, chat_id))
    return ConversationHandler.END


# -------------------------------------------------------------
# CONVERSATION: /add_custom_text
# -------------------------------------------------------------
async def add_custom_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_bot_settings()
    current_text = settings.get("custom_text", "")

    msg = "✏️ Please send the <b>custom text</b>, emojis, or channel link you want appended at the end of every caption."
    if current_text:
        msg += f"\n\n📌 <b>Current Custom Text:</b>\n{current_text}"
    msg += "\n\n<i>Type /cancel to leave unchanged.</i>"

    await update.message.reply_text(msg, parse_mode="HTML")
    return WAITING_FOR_CUSTOM_TEXT


async def receive_custom_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    update_bot_settings({"custom_text": text})

    await update.message.reply_text(
        f"✅ <b>Custom Text Updated Successfully!</b>\n\n"
        f"<b>New Caption Footer:</b>\n{text}",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# -------------------------------------------------------------
# COMMAND: /remove_channel
# -------------------------------------------------------------
async def remove_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide the channel ID. Example: <code>/remove_channel -1001234567890</code>",
            parse_mode="HTML",
        )
        return

    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid Channel ID format. Must be an integer like <code>-100...</code>", parse_mode="HTML")
        return

    success = remove_channel(chat_id)
    if success:
        await update.message.reply_text(
            f"🗑️ Channel <code>{chat_id}</code> has been removed from <code>autoposterbot_db</code>. No further posts will be dispatched there.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(f"❌ Channel <code>{chat_id}</code> was not found in the database.", parse_mode="HTML")


# -------------------------------------------------------------
# COMMAND: /all_channel
# -------------------------------------------------------------
async def all_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = get_all_channels()
    if not channels:
        await update.message.reply_text("📂 No channels connected yet. Use /add_channel to add one.")
        return

    response_text = f"📋 <b>Connected Channels ({len(channels)} total):</b>\n\n"
    for idx, ch in enumerate(channels, 1):
        status_icon = "🟢" if ch.get("status") == "active" else "⏸️"
        response_text += (
            f"{idx}. {status_icon} <b>{ch.get('channel_name', 'N/A')}</b>\n"
            f"   • ID: <code>{ch.get('chat_id')}</code>\n"
            f"   • Total Posts: <b>{ch.get('total_posts', 0)}</b> (✅ {ch.get('success_count', 0)} | ❌ {ch.get('failed_count', 0)})\n"
            f"   • Last Post: {ch.get('last_post_at') or 'Never'}\n\n"
        )

    await update.message.reply_text(response_text, parse_mode="HTML")


# -------------------------------------------------------------
# COMMAND: /test_post
# -------------------------------------------------------------
async def test_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = get_all_channels()
    active_channels = [c for c in channels if c.get("status") == "active"]

    if not active_channels:
        await update.message.reply_text("📂 No active channels connected. Use /add_channel to register one first.")
        return

    status_msg = await update.message.reply_text(f"🚀 Triggering test post to {len(active_channels)} channel(s)...")

    bot = context.bot
    results = []
    for ch in active_channels:
        chat_id = ch["chat_id"]
        res = await post_video_to_channel(bot, chat_id)
        if res.get("success"):
            results.append(f"✅ {ch.get('channel_name')}: Sent post {res.get('post_id')}")
        else:
            results.append(f"❌ {ch.get('channel_name')}: {res.get('error')}")
        await asyncio.sleep(2)

    await status_msg.edit_text(
        "<b>Test Post Results:</b>\n" + "\n".join(results),
        parse_mode="HTML",
    )


# -------------------------------------------------------------
# COMMAND: /stop_posting & /start_posting
# -------------------------------------------------------------
async def stop_posting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_bot_settings({"is_running": False})
    await update.message.reply_text("🛑 <b>Automated Posting Stopped!</b> All scheduled posts are now paused.", parse_mode="HTML")


async def start_posting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_bot_settings({"is_running": True})
    await update.message.reply_text("▶️ <b>Automated Posting Resumed!</b> Hourly posting is active again.", parse_mode="HTML")


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action cancelled.")
    return ConversationHandler.END


# -------------------------------------------------------------
# REGISTER ALL HANDLERS
# -------------------------------------------------------------
def register_bot_handlers(application):
    add_channel_handler = ConversationHandler(
        entry_points=[CommandHandler("add_channel", add_channel_start)],
        states={
            WAITING_FOR_CHANNEL: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_channel_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    custom_text_handler = ConversationHandler(
        entry_points=[CommandHandler("add_custom_text", add_custom_text_start)],
        states={
            WAITING_FOR_CUSTOM_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_text)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(add_channel_handler)
    application.add_handler(custom_text_handler)
    application.add_handler(CommandHandler("remove_channel", remove_channel_command))
    application.add_handler(CommandHandler("all_channel", all_channels_command))
    application.add_handler(CommandHandler("test_post", test_post_command))
    application.add_handler(CommandHandler("stop_posting", stop_posting_command))
    application.add_handler(CommandHandler("start_posting", start_posting_command))
    application.add_handler(CommandHandler("cancel", cancel_conversation))
