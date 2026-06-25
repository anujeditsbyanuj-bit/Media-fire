"""
handlers/downloader.py — Core download + upload logic
"""

import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

import config
import database as db
import mediafire_dl as mf
from utils import human_size, progress_bar, eta_str, is_mediafire_link, split_file, logger

cancel_flags: dict = {}

# Semaphore module level
_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)

PROGRESS_INTERVAL = 3
TG_MAX_BYTES      = 2 * 1024 ** 3   # 2 GB


def register_downloader(app: Client):

    @app.on_message(filters.text & filters.private & ~filters.command(
        ["start", "help", "profile", "history", "ping", "cancel",
         "premium", "redeem", "stats", "genkey", "listkeys", "delkey",
         "addpremium", "revokepremium", "broadcast", "ban", "unban", "users"]
    ))
    async def on_link(c: Client, m: Message):
        if not m.text:
            return

        url = m.text.strip()
        if not is_mediafire_link(url):
            return

        user = m.from_user
        if not user:
            return

        try:
            u = await db.get_user(
                user.id,
                ((user.first_name or "") + (" " + user.last_name if user.last_name else "")).strip()
            )
        except Exception as e:
            logger.error(f"DB error in on_link: {e}")
            await m.reply("❌ Database error. Please try again.")
            return

        if u.get("is_banned", False):
            await m.reply("🚫 You are banned.")
            return

        if not u.get("is_premium", False) and u.get("downloads_today", 0) >= config.FREE_DAILY_LIMIT:
            await m.reply(
                f"⚠️ **Daily limit reached** ({config.FREE_DAILY_LIMIT}/day for free users).\n\n"
                f"👑 Use /premium to upgrade!"
            )
            return

        if user.id in cancel_flags and cancel_flags[user.id] is False:
            await m.reply("⏳ You already have an active download. Use /cancel to stop it.")
            return

        status = await m.reply("🔍 Resolving link…")
        cancel_flags[user.id] = False

        async with _semaphore:
            try:
                if mf.is_folder_link(url):
                    await _handle_folder(c, m, url, u, status)
                else:
                    await _handle_file(c, m, url, u, status)
            except Exception as e:
                logger.exception(f"Unhandled error in download handler: {e}")
                try:
                    await status.edit(f"❌ Unexpected error: `{e}`")
                except Exception:
                    pass
            finally:
                cancel_flags.pop(user.id, None)


def _sanitize(name: str, fallback: str = "file") -> str:
    """Remove bad chars, path traversal, control chars."""
    # FIX 7: Use 'ch' instead of 'c' to avoid shadowing Client param in outer scope
    name = "".join(ch for ch in name if ch not in r'\/:*?"<>|' and ord(ch) >= 32)
    name = name.replace("..", ".")
    return name.strip(". ") or fallback


async def _handle_file(c, m, url, u, status):
    uid = m.from_user.id

    try:
        info = await mf.get_info(url)
    except Exception as e:
        await status.edit(f"❌ Could not resolve link.\n`{e}`")
        return

    if not info or not info.get("url"):
        await status.edit("❌ No download link found. File may be private or deleted.")
        return

    size_bytes = info.get("size") or 0
    size_mb    = size_bytes / (1024 * 1024) if size_bytes else 0
    max_mb     = config.PREMIUM_MAX_SIZE_MB if u.get("is_premium", False) else config.FREE_MAX_SIZE_MB

    # FIX 8: size=0 (unknown) — warn but allow, don't silently bypass
    # Only block if we KNOW the size exceeds limit
    if size_mb and size_mb > max_mb:
        note = "\n👑 Use /premium to upgrade to 4 GB limit." if not u.get("is_premium", False) else ""
        await status.edit(
            f"❌ File too large: **{human_size(size_bytes)}**\n"
            f"Your plan allows max **{max_mb} MB**.{note}"
        )
        return

    filename = _sanitize(info.get("name") or "file")
    dest     = os.path.join(config.DOWNLOAD_DIR, f"{uid}_{filename}")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    size_str = human_size(size_bytes) if size_bytes else "Unknown size"
    await status.edit(
        f"📥 **Starting download…**\n`{filename}`\n"
        f"📦 Size: **{size_str}**"
    )

    start_time = time.time()
    last_edit  = [0.0]

    async def dl_progress(done: int, total: int):
        now = time.time()
        if now - last_edit[0] < PROGRESS_INTERVAL:
            return
        last_edit[0] = now
        elapsed = now - start_time
        speed   = done / elapsed if elapsed else 0
        pct     = done / total * 100 if total else 0
        eta     = int((total - done) / speed) if speed and total else 0
        try:
            await status.edit(
                f"📥 **Downloading…**\n\n"
                f"`{filename}`\n\n"
                f"{progress_bar(pct)} **{pct:.1f}%**\n\n"
                f"⬇️ {human_size(done)} / {human_size(total)}\n"
                f"⚡ {human_size(int(speed))}/s\n"
                f"⏱ ETA: {eta_str(eta)}"
            )
        except Exception:
            pass

    try:
        await mf.download(
            info["url"], dest,
            progress_cb  = dl_progress,
            cancel_check = lambda: cancel_flags.get(uid, False),
        )
    except asyncio.CancelledError:
        await status.edit("🚫 Download cancelled.")
        _rm(dest)
        return
    except Exception as e:
        logger.exception(f"Download failed: {url}")
        await status.edit(f"❌ Download failed.\n`{e}`")
        _rm(dest)
        return

    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        await status.edit("❌ Downloaded file is empty. Please try again.")
        _rm(dest)
        return

    file_size = os.path.getsize(dest)

    # FIX 8b: post-download size check — catches size=0 bypass case
    actual_mb = file_size / (1024 * 1024)
    if actual_mb > max_mb:
        note = "\n👑 Upgrade to Premium for 4 GB limit." if not u.get("is_premium", False) else ""
        await status.edit(
            f"❌ Downloaded file too large: **{human_size(file_size)}**\n"
            f"Your plan allows max **{max_mb} MB**.{note}"
        )
        _rm(dest)
        return

    success = await _upload(c, m, dest, filename, file_size, status, uid)
    if success:
        await db.add_history(uid, filename, human_size(file_size))
    _rm(dest)


async def _upload(c, m, path, name, size, status, uid) -> bool:
    """Returns True on success, False on failure."""
    start_time = time.time()
    last_edit  = [0.0]

    async def up_progress(current: int, total: int):
        now = time.time()
        if now - last_edit[0] < PROGRESS_INTERVAL:
            return
        last_edit[0] = now
        elapsed = now - start_time
        speed   = current / elapsed if elapsed else 0
        pct     = current / total * 100 if total else 0
        eta     = int((total - current) / speed) if speed and total else 0
        try:
            await status.edit(
                f"📤 **Uploading…**\n\n"
                f"`{name}`\n\n"
                f"{progress_bar(pct)} **{pct:.1f}%**\n\n"
                f"⬆️ {human_size(current)} / {human_size(total)}\n"
                f"⚡ {human_size(int(speed))}/s\n"
                f"⏱ ETA: {eta_str(eta)}"
            )
        except Exception:
            pass

    if size <= TG_MAX_BYTES:
        await status.edit(f"📤 **Uploading to Telegram…**\n`{name}`")
        try:
            await c.send_document(
                chat_id   = m.chat.id,
                document  = path,
                file_name = name,
                caption   = f"✅ **{name}**\n📦 {human_size(size)}",
                progress  = up_progress,
            )
            await status.delete()
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            await status.edit(f"❌ Upload failed.\n`{e}`")
            return False

    # File > 2 GB — split
    await status.edit("✂️ File > 2 GB — splitting into parts…")
    parts  = split_file(path, config.SPLIT_SIZE_BYTES)
    all_ok = True
    for i, part in enumerate(parts, 1):
        pname = os.path.basename(part)
        psize = os.path.getsize(part)
        try:
            await status.edit(f"📤 Uploading part {i}/{len(parts)}: `{pname}`")
            await c.send_document(
                chat_id   = m.chat.id,
                document  = part,
                file_name = pname,
                caption   = f"📦 Part {i}/{len(parts)} — {human_size(psize)}",
                progress  = up_progress,
            )
        except Exception as e:
            logger.error(f"Part {i} upload failed: {e}")
            # FIX 9: status.edit after possible delete — wrap safely
            try:
                await status.edit(f"❌ Part {i} failed.\n`{e}`")
            except Exception:
                pass
            all_ok = False
        finally:
            _rm(part)

    if all_ok:
        await m.reply(
            f"✅ All {len(parts)} parts uploaded!\n\n"
            f"**Linux/Mac:**\n`cat {name}.part* > {name}`\n\n"
            f"**Windows CMD:**\n`copy /b {name}.part* {name}`"
        )
        try:
            await status.delete()
        except Exception:
            pass

    return all_ok


async def _handle_folder(c, m, url, u, status):
    if not u.get("is_premium", False):
        await status.edit(
            "📁 **Folder downloads are Premium only.**\n\n"
            "👑 Use /premium to upgrade."
        )
        return

    folder_key = mf.extract_folder_key(url)
    if not folder_key:
        await status.edit("❌ Could not extract folder key from URL.")
        return

    await status.edit("🔍 Scanning folder…")
    try:
        files = await mf.get_folder_files(folder_key)
    except Exception as e:
        await status.edit(f"❌ Folder scan failed.\n`{e}`")
        return

    if not files:
        await status.edit("📭 Folder is empty or private.")
        return

    uid        = m.from_user.id
    max_mb     = config.PREMIUM_MAX_SIZE_MB
    total_size = sum(f.get("size", 0) for f in files)

    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    await status.edit(
        f"📁 Found **{len(files)} files** ({human_size(total_size)}). Starting…"
    )

    for idx, finfo in enumerate(files, 1):
        if cancel_flags.get(uid):
            await status.edit(f"🚫 Cancelled after {idx - 1}/{len(files)} files.")
            return

        fname = finfo.get("name", "file")
        await status.edit(f"📥 File {idx}/{len(files)}: `{fname}`")

        try:
            page_url = finfo.get("page_url") or (
                f"https://www.mediafire.com/file/{finfo.get('key', '')}" if finfo.get("key") else ""
            )
            if not page_url:
                await m.reply(f"⚠️ Skipped (no link): `{fname}`")
                continue
            info = await mf.get_info(page_url)
            if not info or not info.get("url"):
                await m.reply(f"⚠️ Skipped (no link): `{fname}`")
                continue
        except Exception as e:
            await m.reply(f"⚠️ Skipped `{fname}`: `{e}`")
            continue

        # FIX 8 (folder): same size=0 bypass fix — check actual size post-download
        f_size_bytes = info.get("size") or 0
        f_size_mb    = f_size_bytes / (1024 * 1024) if f_size_bytes else 0
        if f_size_mb and f_size_mb > max_mb:
            await m.reply(
                f"⚠️ Skipped `{fname}` — too large: **{human_size(f_size_bytes)}** "
                f"(max {max_mb} MB)"
            )
            continue

        safe_name = _sanitize(info["name"])
        dest      = os.path.join(config.DOWNLOAD_DIR, f"{uid}_{safe_name}")
        try:
            await mf.download(
                info["url"], dest,
                cancel_check=lambda u=uid: cancel_flags.get(u, False),
            )
            if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                await m.reply(f"⚠️ Empty file, skipped: `{fname}`")
                continue

            fsize     = os.path.getsize(dest)
            # FIX 8b (folder): post-download actual size check
            actual_mb = fsize / (1024 * 1024)
            if actual_mb > max_mb:
                await m.reply(
                    f"⚠️ Skipped `{fname}` after download — actual size {human_size(fsize)} "
                    f"exceeds {max_mb} MB limit."
                )
                continue

            success = await _upload(c, m, dest, safe_name, fsize, status, uid)
            if success:
                await db.add_history(uid, safe_name, human_size(fsize))
        except asyncio.CancelledError:
            await status.edit("🚫 Cancelled.")
            _rm(dest)
            return
        except Exception as e:
            await m.reply(f"❌ Failed `{fname}`: `{e}`")
        finally:
            _rm(dest)

    await m.reply(f"✅ Folder done! {len(files)} files processed.")


def _rm(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
