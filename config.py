"""
config.py — Bot configuration
Sab values environment variables se aati hain (Replit Secrets mein set karo)
"""

import os

# ── Telegram credentials ───────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
API_ID      = int(os.environ.get("API_ID", "0"))
API_HASH    = os.environ.get("API_HASH", "")
OWNER_ID    = int(os.environ.get("OWNER_ID", "0"))

# ── Bot branding ───────────────────────────────────────────────────────────────
BOT_NAME         = os.environ.get("BOT_NAME", "Mediafire Bot")
ADMIN_NAME       = os.environ.get("ADMIN_NAME", "Admin")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")
OWNER_USERNAME   = os.environ.get("OWNER_USERNAME", "")

# ── Download limits ────────────────────────────────────────────────────────────
FREE_DAILY_LIMIT    = 7
FREE_MAX_SIZE_MB    = 500
PREMIUM_MAX_SIZE_MB = 4096

# ── Paths ──────────────────────────────────────────────────────────────────────
DOWNLOAD_DIR = "downloads"
LOG_FILE     = "logs/bot.log"

# ── Queue ──────────────────────────────────────────────────────────────────────
MAX_CONCURRENT_DOWNLOADS = 3

# ── File splitting ─────────────────────────────────────────────────────────────
SPLIT_SIZE_BYTES = 1_900 * 1024 * 1024  # 1.9 GB per part

# ── MongoDB Atlas ──────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB  = os.environ.get("MONGO_DB", "mediafire_bot")
MONGO_COL = os.environ.get("MONGO_COL", "users")

