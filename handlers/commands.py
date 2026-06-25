"""
handlers/commands.py — User commands (Pyrogram)
"""

import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import config
import database as db
from utils import logger


def _full_name(user) -> str:
    first = user.first_name or ""
    last  = user.last_name or ""
    return (first + " " + last).strip() if last else first


def _channel_url() -> str:
    ch = config.CHANNEL_USERNAME.lstrip("@")
    # FIX 1: Invalid URL guard — Telegram rejects bare https://t.me/
    return f"https://t.me/{ch}" if ch else None


def register_commands(app: Client):

    # ── /start ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command("start") & filters.private)
    async def cmd_start(c: Client, m: Message):
        try:
            u = await db.get_user(m.from_user.id, _full_name(m.from_user))
        except Exception as e:
            logger.error(f"DB error in /start: {e}")
            await m.reply("❌ Database error. Please try again.")
            return

        is_prem = u.get("is_premium", False)
        plan    = "👑 Premium" if is_prem else "🆓 Free"
        dl      = "♾ Unlimited" if is_prem else f"{u.get('downloads_today', 0)} / {config.FREE_DAILY_LIMIT}"
        max_size = config.PREMIUM_MAX_SIZE_MB if is_prem else config.FREE_MAX_SIZE_MB

        exp_line = ""
        if u.get("is_premium") and u.get("premium_expiry"):
            try:
                exp = datetime.fromisoformat(u["premium_expiry"])
                exp_line = f"\n**Premium expires:** {exp.strftime('%d %b %Y')}"
            except Exception:
                pass

        # FIX 1: Only add Channel button if URL is valid
        ch_url = _channel_url()
        buttons = [
            [InlineKeyboardButton("📖 Help",        callback_data="cb_help"),
             InlineKeyboardButton("👤 Profile",     callback_data="cb_profile")],
            [InlineKeyboardButton("👑 Get Premium", callback_data="cb_premium")],
        ]
        if ch_url:
            buttons[1].append(InlineKeyboardButton("📢 Channel", url=ch_url))
        kb = InlineKeyboardMarkup(buttons)

        await m.reply(
            f"👋 **Welcome to {config.BOT_NAME}!**\n\n"
            f"Download files & folders from **Mediafire** directly to Telegram.\n"
            f"Made with ❤️ by **{config.ADMIN_NAME}**\n\n"
            f"🔗 Just send me any Mediafire link!\n\n"
            f"**What I support:**\n"
            f"• 📄 Single file downloads (up to {max_size} MB)\n"
            f"• 📁 Full folder downloads {'✅' if is_prem else '(Premium only)'}\n"
            f"• ⚡ Live speed + ETA progress bar\n"
            f"• 🚫 Cancel anytime with /cancel\n\n"
            f"**Your Plan:** {plan}{exp_line}\n"
            f"**Downloads today:** {dl}\n\n"
            f"Use /help for all commands.",
            reply_markup=kb,
        )

    # ── /help ─────────────────────────────────────────────────────────────────
    @app.on_message(filters.command("help") & filters.private)
    async def cmd_help(c: Client, m: Message):
        await m.reply(
            f"📖 **{config.BOT_NAME} — Help**\n\n"
            f"🔗 **How to download:**\n"
            f"Send any `mediafire.com/file/` or `mediafire.com/folder/` link.\n\n"
            f"📋 **Commands:**\n"
            f"• /start — Welcome screen\n"
            f"• /help — This page\n"
            f"• /profile — Your stats & plan\n"
            f"• /history — Last 20 downloads\n"
            f"• /cancel — Cancel active download\n"
            f"• /ping — Bot latency\n"
            f"• /premium — Plans & benefits\n"
            f"• /redeem KEY — Activate a premium key\n\n"
            f"⚡ **Premium Benefits:**\n"
            f"• Unlimited daily downloads (free: {config.FREE_DAILY_LIMIT}/day)\n"
            f"• Files up to {config.PREMIUM_MAX_SIZE_MB} MB (4 GB)\n"
            f"• Folder downloads\n"
            f"• Priority queue\n\n"
            f"👨‍💻 **Admin:** {config.ADMIN_NAME}\n"
            f"💬 **Support:** {config.CHANNEL_USERNAME}"
        )

    # ── /profile ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command("profile") & filters.private)
    async def cmd_profile(c: Client, m: Message):
        try:
            u = await db.get_user(m.from_user.id, _full_name(m.from_user))
        except Exception as e:
            logger.error(f"DB error in /profile: {e}")
            await m.reply("❌ Database error. Please try again.")
            return

        is_prem = u.get("is_premium", False)
        plan    = "👑 Premium" if is_prem else "🆓 Free"
        dl      = "♾ Unlimited" if is_prem else f"{u.get('downloads_today', 0)} / {config.FREE_DAILY_LIMIT}"

        exp_line = ""
        if u.get("is_premium") and u.get("premium_expiry"):
            try:
                exp = datetime.fromisoformat(u["premium_expiry"])
                exp_line = f"\n**Expires:** {exp.strftime('%d %b %Y %H:%M')}"
            except Exception:
                pass
        elif u.get("is_premium"):
            exp_line = "\n**Expires:** Never (Lifetime)"

        await m.reply(
            f"👤 **Your Profile**\n\n"
            f"**Name:** {_full_name(m.from_user)}\n"
            f"**ID:** `{m.from_user.id}`\n"
            f"**Plan:** {plan}{exp_line}\n"
            f"**Downloads today:** {dl}\n"
            f"**Total downloads:** {u.get('total_downloads', 0)}\n"
            f"**Joined:** {u.get('joined', 'N/A')}\n\n"
            f"👨‍💻 Bot by **{config.ADMIN_NAME}** | {config.CHANNEL_USERNAME}"
        )

    # ── /history ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command("history") & filters.private)
    async def cmd_history(c: Client, m: Message):
        try:
            u = await db.get_user(m.from_user.id, _full_name(m.from_user))
        except Exception as e:
            logger.error(f"DB error in /history: {e}")
            await m.reply("❌ Database error. Please try again.")
            return

        if not u.get("history"):
            await m.reply("📭 You haven't downloaded anything yet.")
            return

        # FIX 2: Truncate filename to avoid 4096-char Telegram limit
        lines = ["📋 **Your last 20 downloads:**\n"]
        for i, h in enumerate(u.get("history", [])[:20], 1):
            name = h.get("name", "?")
            if len(name) > 40:
                name = name[:37] + "..."
            lines.append(f"{i}. `{name}` — {h.get('size','?')} — {h.get('date','?')}")

        text = "\n".join(lines)
        # Extra safety — hard truncate if still too long
        if len(text) > 4000:
            text = text[:4000] + "\n…(truncated)"
        await m.reply(text)

    # ── /ping ─────────────────────────────────────────────────────────────────
    @app.on_message(filters.command("ping") & filters.private)
    async def cmd_ping(c: Client, m: Message):
        t0  = time.time()
        msg = await m.reply("🏓 Pinging…")
        ms  = int((time.time() - t0) * 1000)
        await msg.edit(f"🏓 **Pong!**\n⚡ Latency: **{ms}ms**\n\n👨‍💻 {config.BOT_NAME}")

    # ── /cancel ───────────────────────────────────────────────────────────────
    @app.on_message(filters.command("cancel") & filters.private)
    async def cmd_cancel(c: Client, m: Message):
        from handlers.downloader import cancel_flags
        uid = m.from_user.id
        if uid in cancel_flags:
            cancel_flags[uid] = True
            await m.reply("🚫 Cancelling… please wait.")
        else:
            await m.reply("❌ No active download to cancel.")

    # ── /premium ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command("premium") & filters.private)
    async def cmd_premium(c: Client, m: Message):
        owner = f"@{config.OWNER_USERNAME.lstrip('@')}" if config.OWNER_USERNAME else "the admin"
        await m.reply(
            f"👑 **{config.BOT_NAME} — Premium Plans**\n\n"
            f"**🆓 Free Plan:**\n"
            f"• {config.FREE_DAILY_LIMIT} downloads / day\n"
            f"• Max file: {config.FREE_MAX_SIZE_MB} MB\n\n"
            f"**👑 Premium Plan:**\n"
            f"• ♾ Unlimited downloads\n"
            f"• Max file: {config.PREMIUM_MAX_SIZE_MB} MB (4 GB)\n"
            f"• Folder downloads\n"
            f"• Priority queue\n\n"
            f"🔑 Have a key? `/redeem YOUR_KEY`\n\n"
            f"📩 **Buy from {config.ADMIN_NAME}:** {owner}"
        )

    # ── /redeem ───────────────────────────────────────────────────────────────
    @app.on_message(filters.command("redeem") & filters.private)
    async def cmd_redeem(c: Client, m: Message):
        uid   = m.from_user.id
        args  = m.text.split(maxsplit=1)
        owner = f"@{config.OWNER_USERNAME.lstrip('@')}" if config.OWNER_USERNAME else "the admin"

        if len(args) < 2:
            await m.reply(
                f"❌ **Usage:** `/redeem YOUR_KEY`\n\n"
                f"📩 Key khareedne ke liye contact karo: {owner}"
            )
            return

        key = args[1].strip().upper()
        try:
            result = await db.redeem_key(key, uid)
        except Exception as e:
            logger.error(f"DB error in /redeem: {e}")
            await m.reply("❌ Database error. Please try again.")
            return

        if not result["ok"]:
            msgs = {
                "invalid": f"❌ Invalid key.\n📩 Valid key ke liye contact karo: {owner}",
                "used":    "⚠️ Ye key kisi aur ne already use kar li hai.",
                "own":     "⚠️ Aapne ye key pehle se use kar rakhi hai.",
            }
            await m.reply(msgs.get(result["reason"], "❌ Key redeem nahi ho saki."))
            return

        days   = result["days"]
        expiry = result["expiry"]
        await m.reply(
            f"✅ **Premium Activated!**\n\n"
            f"⏳ Duration: **{days} day{'s' if days > 1 else ''}**\n"
            f"📅 Expires: **{expiry.strftime('%d %b %Y %H:%M')}**\n\n"
            f"Enjoy karo! 🎉\n"
            f"👨‍💻 **{config.ADMIN_NAME}** ki taraf se 💙"
        )
        logger.info(f"User {uid} redeemed key {key} ({days} days)")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    # FIX 3: Filter only known callback_data — avoids conflicts with other handlers
    @app.on_callback_query(filters.regex(r"^cb_(help|profile|premium)$"))
    async def on_callback(c: Client, cb: CallbackQuery):
        try:
            await cb.answer()
        except Exception:
            pass

        # FIX 4: cb.message can be None (deleted/inline message)
        if not cb.message:
            return

        if cb.data == "cb_help":
            await cb.message.reply(
                f"📖 Send any `mediafire.com` link to download.\n"
                f"Use /help for full details.\n\n"
                f"👨‍💻 Bot by **{config.ADMIN_NAME}**"
            )
        elif cb.data == "cb_profile":
            try:
                u    = await db.get_user(cb.from_user.id, _full_name(cb.from_user))
                plan = "👑 Premium" if u.get("is_premium", False) else "🆓 Free"
                await cb.message.reply(
                    f"👤 **Your Profile**\n"
                    f"**Name:** {_full_name(cb.from_user)}\n"
                    f"**Plan:** {plan}\n"
                    f"**Total downloads:** {u.get('total_downloads', 0)}"
                )
            except Exception as e:
                logger.error(f"DB error in cb_profile: {e}")
                await cb.message.reply("❌ Database error.")
        elif cb.data == "cb_premium":
            owner = f"@{config.OWNER_USERNAME.lstrip('@')}" if config.OWNER_USERNAME else "the admin"
            await cb.message.reply(
                f"👑 Use /premium for plans.\n"
                f"📩 Buy from **{config.ADMIN_NAME}**: {owner}"
            )
