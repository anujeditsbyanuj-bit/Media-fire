"""
config.py — Bot configuration
Sab values environment variables se aati hain (Replit Secrets mein set karo)
"""

import os

# ── Telegram credentials ───────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "8667684753:AAFbJbj4VWBZHvMlZ525elePDU-cdKasu7o")
API_ID      = int(os.environ.get("API_ID", "37476811"))
API_HASH    = os.environ.get("API_HASH", "7aa60670b871050820086c6267371ee6")
OWNER_ID    = int(os.environ.get("OWNER_ID", "8730393744"))

# ── Bot branding ───────────────────────────────────────────────────────────────
BOT_NAME         = os.environ.get("BOT_NAME", "Mediafire Bot")
ADMIN_NAME       = os.environ.get("ADMIN_NAME", "Anuj")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@log_ak_bots")
OWNER_USERNAME   = os.environ.get("OWNER_USERNAME", "@anujedits76")

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
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Anujedit:Anujedit@cluster0.7cs2nhd.mongodb.net/?appName=Cluster0")
MONGO_DB  = os.environ.get("MONGO_DB", "Anujedit")
MONGO_COL = os.environ.get("MONGO_COL", "Anujedit")

