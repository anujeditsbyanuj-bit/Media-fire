"""
handlers/admin.py — Admin commands (Pyrogram, owner only)
"""

import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message

import config
import database as db
from utils import logger

try:
    from pyrogram.errors import FloodWait
except ImportError:
    FloodWait = None


def _parse_uid(s: str):
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def register_admin(app: Client):

    # ── /stats ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command("stats") & filters.private)
    async def cmd_stats(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        try:
            s = await db.get_stats()
        except Exception as e:
            logger.error(f"DB error in /stats: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        await m.reply(
            f"📊 **Bot Statistics**\n\n"
            f"👥 Total users: **{s['total_users']}**\n"
            f"👑 Premium active: **{s['premium_users']}**\n"
            f"🚫 Banned: **{s['banned_users']}**\n"
            f"🟢 Active today: **{s['active_today']}**\n"
            f"📥 Total downloads: **{s['total_downloads']}**"
        )

    # ── /genkey ───────────────────────────────────────────────────────────────
    @app.on_message(filters.command("genkey") & filters.private)
    async def cmd_genkey(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await m.reply(
                "❌ **Usage:**\n"
                "`/genkey 1`   — 1 day key\n"
                "`/genkey 7`   — 7 day key\n"
                "`/genkey 30`  — 30 day key\n"
                "`/genkey 7 3` — 3 keys of 7 days"
            )
            return

        days  = int(args[1])
        # FIX 5: days=0 guard — 0 din ka key useless hai
        if days < 1:
            await m.reply("❌ Days must be at least 1.")
            return

        count = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 1
        count = min(count, 20)

        keys = []
        for _ in range(count):
            try:
                k = await db.create_key(days)
                keys.append(k)
            except Exception as e:
                logger.error(f"DB error in /genkey: {e}")
                await m.reply("❌ Database error while generating keys. Please try again.")
                return

        day_label = f"{days} day{'s' if days > 1 else ''}"
        lines     = [f"🔑 **Generated {count} key(s) — {day_label} each:**\n"]
        for k in keys:
            lines.append(f"`{k}`")
        lines.append(f"\n📋 User ko bhejo, woh `/redeem KEY` se activate karega.")
        await m.reply("\n".join(lines))
        logger.info(f"Admin generated {count}x {days}-day keys")

    # ── /listkeys ─────────────────────────────────────────────────────────────
    @app.on_message(filters.command("listkeys") & filters.private)
    async def cmd_listkeys(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return

        args      = m.text.split()
        show_used = "all" in args

        page = 1
        for a in args[1:]:
            if a.isdigit():
                page = max(1, int(a))
                break

        try:
            keys = await db.list_keys(show_used=show_used)
        except Exception as e:
            logger.error(f"DB error in /listkeys: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        if not keys:
            await m.reply("📭 Koi key nahi mili." + (" (unused)" if not show_used else ""))
            return

        PAGE_SIZE   = 30
        total_pages = max(1, (len(keys) + PAGE_SIZE - 1) // PAGE_SIZE)
        page        = min(page, total_pages)
        start       = (page - 1) * PAGE_SIZE
        page_keys   = keys[start: start + PAGE_SIZE]

        lines = [f"🔑 **Keys** ({'all' if show_used else 'unused only'}) — Page {page}/{total_pages}:\n"]
        for k in page_keys:
            badge     = "✅ Used" if k["used"] else "🟢 Available"
            used_info = f" → `{k['used_by']}`" if k["used"] else ""
            lines.append(f"{badge} | **{k['days']}d** | `{k['key']}`{used_info}")
        lines.append(f"\nTotal: {len(keys)}")
        if total_pages > 1:
            cmd = "all " if show_used else ""
            lines.append(f"_Next: `/listkeys {cmd}{page + 1}`_")
        if not show_used:
            lines.append("_Used keys bhi: `/listkeys all`_")
        await m.reply("\n".join(lines))

    # ── /delkey ───────────────────────────────────────────────────────────────
    @app.on_message(filters.command("delkey") & filters.private)
    async def cmd_delkey(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        if len(args) < 2:
            await m.reply("❌ Usage: `/delkey XYLON-XXXX-XXXX-XXXX`")
            return
        key = args[1].strip()
        try:
            ok = await db.delete_key(key)
        except Exception as e:
            logger.error(f"DB error in /delkey: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        await m.reply(f"🗑 Key deleted:\n`{key}`" if ok else "❌ Key nahi mili ya already used hai.")

    # ── /addpremium ───────────────────────────────────────────────────────────
    @app.on_message(filters.command("addpremium") & filters.private)
    async def cmd_addpremium(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        uid  = _parse_uid(args[1]) if len(args) >= 2 else None
        if uid is None:
            await m.reply(
                "❌ **Usage:**\n"
                "`/addpremium USER_ID`     — lifetime\n"
                "`/addpremium USER_ID 7`   — 7 days\n"
                "`/addpremium USER_ID 30`  — 30 days"
            )
            return

        # FIX 5: days=0 treated as lifetime was a bug — now explicitly guard
        raw_days = _parse_uid(args[2]) if len(args) >= 3 else None
        days     = raw_days if raw_days and raw_days > 0 else None

        if days:
            expiry     = datetime.now() + timedelta(days=days)
            await db.set_premium(uid, True, expiry)
            exp_str    = expiry.strftime("%d %b %Y")
            plan_label = f"**{days} days** (expires {exp_str})"
            notify_msg = f"🎉 You've been granted **{days}-day Premium** by the admin!\nExpires: {exp_str}"
        else:
            await db.set_premium(uid, True, None)
            plan_label = "**Lifetime**"
            notify_msg = "🎉 You've been granted **Lifetime Premium** by the admin!"

        await m.reply(f"👑 User `{uid}` → Premium {plan_label}")
        try:
            await c.send_message(uid, notify_msg)
        except Exception:
            pass
        logger.info(f"Admin granted premium to {uid}, days={days}")

    # ── /revokepremium ────────────────────────────────────────────────────────
    @app.on_message(filters.command("revokepremium") & filters.private)
    async def cmd_revokepremium(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        uid  = _parse_uid(args[1]) if len(args) >= 2 else None
        if uid is None:
            await m.reply("❌ Usage: `/revokepremium USER_ID`")
            return
        await db.set_premium(uid, False)
        await m.reply(f"❌ Premium revoked for `{uid}`.")
        try:
            await c.send_message(uid, "⚠️ Aapka premium access revoke kar diya gaya hai.")
        except Exception:
            pass

    # ── /broadcast ────────────────────────────────────────────────────────────
    @app.on_message(filters.command("broadcast") & filters.private)
    async def cmd_broadcast(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split(maxsplit=1)
        if len(args) < 2:
            await m.reply("❌ Usage: `/broadcast Your message`")
            return

        msg    = args[1]
        # Truncate if too long — Telegram max 4096, prefix = 20 chars
        MAX_MSG = 4096 - 20
        if len(msg) > MAX_MSG:
            msg = msg[:MAX_MSG - 3] + "…"
        users  = await db.get_all_users()
        sent   = failed = 0
        status = await m.reply(f"📢 Broadcasting to {len(users)} users…")

        for u in users:
            if u.get("is_banned"):
                continue
            try:
                await c.send_message(u.get("uid"), f"📢 **Announcement**\n\n{msg}")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                if FloodWait and isinstance(e, FloodWait):
                    wait = getattr(e, "value", getattr(e, "x", 5)) + 1
                    logger.warning(f"FloodWait {wait}s during broadcast")
                    await asyncio.sleep(wait)
                    try:
                        await c.send_message(u.get("uid"), f"📢 **Announcement**\n\n{msg}")
                        sent += 1
                    except Exception:
                        failed += 1
                else:
                    failed += 1

        await status.edit(f"📢 **Done**\n✅ Sent: {sent}\n❌ Failed: {failed}")

    # ── /ban / /unban ─────────────────────────────────────────────────────────
    @app.on_message(filters.command("ban") & filters.private)
    async def cmd_ban(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        uid  = _parse_uid(args[1]) if len(args) >= 2 else None
        if uid is None:
            await m.reply("❌ Usage: `/ban USER_ID`"); return
        try:
            await db.set_banned(uid, True)
        except Exception as e:
            logger.error(f"DB error in /ban: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        await m.reply(f"🚫 User `{uid}` banned.")

    @app.on_message(filters.command("unban") & filters.private)
    async def cmd_unban(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        args = m.text.split()
        uid  = _parse_uid(args[1]) if len(args) >= 2 else None
        if uid is None:
            await m.reply("❌ Usage: `/unban USER_ID`"); return
        try:
            await db.set_banned(uid, False)
        except Exception as e:
            logger.error(f"DB error in /unban: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        await m.reply(f"✅ User `{uid}` unbanned.")

    # ── /users ────────────────────────────────────────────────────────────────
    @app.on_message(filters.command("users") & filters.private)
    async def cmd_users(c: Client, m: Message):
        if m.from_user.id != config.OWNER_ID:
            await m.reply("⛔ Owner only."); return
        try:
            users = await db.get_all_users()
        except Exception as e:
            logger.error(f"DB error in /users: {e}")
            await m.reply("❌ Database error. Please try again.")
            return
        if not users:
            await m.reply("No users yet."); return
        # FIX 6: Sort by joined/total downloads for consistent ordering
        # MongoDB .find() has no guaranteed order — slice [-20:] was random
        recent = sorted(users, key=lambda x: x.get("total_downloads", 0), reverse=True)[:20]
        lines  = ["👥 **User List** (top 20 by downloads):\n"]
        for u in recent:
            badge = "👑" if u.get("is_premium") else ("🚫" if u.get("is_banned") else "👤")
            exp   = f" — exp: {u['premium_expiry'][:10]}" if u.get("premium_expiry") else ""
            lines.append(f"{badge} `{u['uid']}` — {u.get('name','?')} — {u.get('total_downloads',0)} DLs{exp}")
        await m.reply("\n".join(lines))
