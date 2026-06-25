"""
bot.py — Xylon Mediafire Downloader Bot (Pyrogram)
"""

import asyncio
import os
import glob
from pyrogram import Client, idle
from pyrogram.types import BotCommand

import config
import database as db
from utils import logger
from handlers.commands import register_commands
from handlers.admin    import register_admin
from handlers.downloader import register_downloader


def build_app() -> Client:
    return Client(
        name        = "xylon_bot",
        api_id      = config.API_ID,
        api_hash    = config.API_HASH,
        bot_token   = config.BOT_TOKEN,
        workers     = 4,
    )


async def set_commands(app: Client):
    await app.set_bot_commands([
        BotCommand("start",         "Welcome screen"),
        BotCommand("help",          "All commands & usage"),
        BotCommand("profile",       "Your stats & plan"),
        BotCommand("history",       "Last 20 downloads"),
        BotCommand("ping",          "Bot latency check"),
        BotCommand("cancel",        "Cancel active download"),
        BotCommand("premium",       "Premium plans & benefits"),
        BotCommand("redeem",        "Redeem a premium key"),
        BotCommand("genkey",        "🔑 [Admin] Generate redeem key"),
        BotCommand("listkeys",      "📋 [Admin] List all keys"),
        BotCommand("delkey",        "🗑 [Admin] Delete unused key"),
        BotCommand("stats",         "📊 [Admin] Bot statistics"),
        BotCommand("broadcast",     "📢 [Admin] Message all users"),
        BotCommand("ban",           "🚫 [Admin] Ban a user"),
        BotCommand("unban",         "✅ [Admin] Unban a user"),
        BotCommand("addpremium",    "👑 [Admin] Grant premium"),
        BotCommand("revokepremium", "❌ [Admin] Revoke premium"),
        BotCommand("users",         "👥 [Admin] List users"),
    ])


async def main():
    # ── Create required directories ───────────────────────────────────────────
    for d in [config.DOWNLOAD_DIR, "data", "logs"]:
        os.makedirs(d, exist_ok=True)

    # ── Validate config ───────────────────────────────────────────────────────
    missing = []
    if not config.BOT_TOKEN:  missing.append("BOT_TOKEN")
    if not config.API_ID:     missing.append("API_ID")
    if not config.API_HASH:   missing.append("API_HASH")
    if not config.MONGO_URI:  missing.append("MONGO_URI")

    if missing:
        print(f"❌ Replit Secrets mein yeh set karo: {', '.join(missing)}")
        return

    if not config.OWNER_ID:
        print("⚠️  OWNER_ID set nahi — admin commands kaam nahi karenge!")

    # ── Purani session files delete karo (double response fix) ───────────────
    for f in glob.glob("*.session") + glob.glob("*.session-journal"):
        try:
            os.remove(f)
            logger.info(f"Deleted stale session: {f}")
        except Exception:
            pass

    # ── Build app ─────────────────────────────────────────────────────────────
    app = build_app()

    # ── Register handlers (sirf ek baar) ─────────────────────────────────────
    register_commands(app)
    register_admin(app)
    register_downloader(app)

    # ── Start ─────────────────────────────────────────────────────────────────
    async with app:
        me = await app.get_me()
        await set_commands(app)
        logger.info(f"✅ Bot running: @{me.username}")
        print(f"✅ Bot started: @{me.username}")
        await idle()

    await db.close()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
