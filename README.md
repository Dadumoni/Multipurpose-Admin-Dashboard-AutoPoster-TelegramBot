# Telegram Auto-Poster Bot (Supabase & Render Edition)

Automated multi-channel Telegram video broadcaster engine. Posts video streams sequentially from your Supabase `viralhub_db` catalog to all connected Telegram channels, tracks post counts, and provides a REST API to be monitored and controlled directly from your **Multipurpose Admin Dashboard**.

---

## 🚀 Key Features

- **100% Supabase Single-Database & Single-Table Architecture**: Zero reliance on MongoDB.
  - Channels, statistics, and global bot settings stored in a single table `autoposterbot_db`.
  - Video catalog fetched directly from `viralhub_db`.
- **Render Deployment Ready**: Built with **FastAPI** + **python-telegram-bot** + **APScheduler** in a single async process. Includes health checks (`/health`) and dynamic port binding (`$PORT`) required by Render Web Services.
- **Remote Control REST API**: Enables the Admin Dashboard to start/stop the bot, trigger instant posts, add/remove channels, and change posting frequency remotely over HTTP.
- **Initial 10-Post Burst**: When a new channel is registered (via `/add_channel` in Telegram or via the Admin Dashboard), the bot automatically posts 10 initial videos with a 10-second gap.
- **Automated Scheduling**: Sequentially broadcasts random unposted videos to all active channels every hour (or at custom configurable intervals) with a 5-second interval between channels to avoid Telegram rate limits.
- **Smart History Tracking**: Keeps track of `posted_ids` per channel to prevent duplicate video postings. Automatically resets history when all available videos have been broadcast.

---

## 📁 Repository Structure

```
Multipurpose-Admin-Dashboard-AutoPoster-TelegramBot/
├── api/
│   ├── __init__.py
│   └── routes.py              # REST API endpoints for Admin Dashboard (/health, /api/status, /api/control, etc.)
├── bot/
│   ├── __init__.py
│   ├── bot_app.py             # python-telegram-bot Application lifecycle
│   └── handlers.py            # Telegram command & conversation handlers (/start, /add_channel, etc.)
├── database/
│   ├── __init__.py
│   └── supabase_client.py     # All Supabase operations (autoposterbot_db, viralhub_db, settings)
├── services/
│   ├── __init__.py
│   ├── poster.py              # Video selection, HTML caption formatting, and Telegram delivery
│   └── scheduler.py           # APScheduler background tasks & 10-post initial burst
├── config.py                  # Environment settings & logging setup
├── main.py                    # Entrypoint: boots FastAPI + Telegram Bot + Scheduler
├── requirements.txt           # Python dependencies
├── Procfile                   # Process file for Render / PaaS deployment
├── render.yaml                # Render Blueprint file
├── .env.example               # Example configuration
└── README.md
```

---

## 🛠️ Deploying to Render (Step-by-Step)

### Option 1: One-Click / Web Service Deployment

1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New +** -> **Web Service**.
2. Connect your GitHub repository:
   `https://github.com/Dadumoni/Multipurpose-Admin-Dashboard-AutoPoster-TelegramBot`
3. Configure the service settings:
   - **Name**: `autoposter-telegram-bot`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
4. Add the following **Environment Variables**:
   | Variable | Value / Description |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | Your Telegram Bot Token from `@BotFather` |
   | `SUPABASE_URL` | Your Supabase Project URL (`https://aswphdoqnayyacivxebf.supabase.co`) |
   | `SUPABASE_KEY` | Your Supabase `service_role` or `anon` key |
   | `STREAMING_URL` | Video streaming base URL (e.g. `https://viralhub.space`) |
5. Click **Create Web Service**.
6. Once deployed, Render will provide a public URL like:
   `https://autoposter-telegram-bot.onrender.com`
7. Copy this URL and add it to your **Admin Dashboard `.env`**:
   ```env
   TELEGRAM_POSTER_BOT_URL=https://autoposter-telegram-bot.onrender.com
   ```

---

## 🤖 Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome status, current posting frequency, and command guide. |
| `/add_channel` | Interactive prompt to forward a message or send a Channel ID (e.g. `-100...`). Automatically begins the 10-video initial burst. |
| `/remove_channel <id>` | Removes a channel from `autoposterbot_db`. |
| `/all_channel` | Lists all connected channels with total, success, and failed post statistics. |
| `/add_custom_text` | Interactive prompt to set custom footer text or channel links appended to every video caption. |
| `/test_post` | Immediately dispatches a test video to all active channels. |
| `/stop_posting` | Pauses automated scheduled posting across all channels. |
| `/start_posting` | Resumes automated scheduled posting across all channels. |
| `/cancel` | Cancels any ongoing conversation. |

---

## 🌐 Admin Dashboard REST API Endpoints

The FastAPI web service exposes the following endpoints used by your Admin Dashboard:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check for Render and uptime monitoring. |
| `GET` | `/api/status` | Current bot status (Online/Offline), channels, custom caption, and posting frequency. |
| `POST` | `/api/control/start` | Resumes automated posting. |
| `POST` | `/api/control/stop` | Pauses automated posting. |
| `POST` | `/api/control/post-now` | Triggers an immediate post to one or all channels. |
| `GET` | `/api/channels` | Returns all registered channels with their real-time stats. |
| `POST` | `/api/channels` | Adds a new channel from the dashboard. |
| `POST` | `/api/channels/{id}/toggle` | Pauses or activates a channel. |
| `DELETE`| `/api/channels/{id}` | Deletes a channel from the database. |
| `POST` | `/api/settings/custom-text` | Updates custom caption footer text. |
| `POST` | `/api/settings/hourly-rate` | Updates hourly posting frequency. |

---

## 💻 Local Development

1. Clone repository:
   ```bash
   git clone https://github.com/Dadumoni/Multipurpose-Admin-Dashboard-AutoPoster-TelegramBot.git
   cd Multipurpose-Admin-Dashboard-AutoPoster-TelegramBot
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your credentials.
5. Run the bot:
   ```bash
   python main.py
   ```
