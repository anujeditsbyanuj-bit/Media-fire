"""
utils.py — Shared helper functions
"""

import os
import re
import math
import logging
import config

# ── Logger ────────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

# BUG FIX: basicConfig only works once — use getLogger properly to avoid
# duplicate log lines when module is reloaded
logger = logging.getLogger("xylon")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh  = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh  = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


# ── Text helpers ──────────────────────────────────────────────────────────────
def human_size(b) -> str:
    # BUG FIX: b could be float after division — handle None/0 safely
    try:
        b = int(b)
    except (TypeError, ValueError):
        return "Unknown"
    if b <= 0:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def progress_bar(pct: float, width: int = 16) -> str:
    # BUG FIX: clamp pct to 0-100 to avoid negative filled or overflow
    pct    = max(0.0, min(100.0, pct))
    filled = math.floor(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def esc(text: str) -> str:
    """Escape special chars for MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def eta_str(seconds: int) -> str:
    # BUG FIX: handle negative/very large values
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "?"
    if seconds <= 0:
        return "0s"
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def is_mediafire_link(text: str) -> bool:
    # BUG FIX: strip and check text is not None
    if not text:
        return False
    return bool(re.search(r"mediafire\.com/(file|folder)/", text.strip(), re.I))


# ── File splitter ─────────────────────────────────────────────────────────────
def split_file(filepath: str, chunk_size: int = config.SPLIT_SIZE_BYTES) -> list:
    """Split a large file into parts. Returns list of part paths."""
    parts = []
    with open(filepath, "rb") as src:
        i = 1
        while True:
            data = src.read(chunk_size)
            if not data:
                break
            part_path = f"{filepath}.part{i:02d}"
            with open(part_path, "wb") as pf:
                pf.write(data)
            parts.append(part_path)
            i += 1
    return parts


def reassembly_guide(filename: str) -> str:
    base = esc(filename)
    return (
        "📋 *File Reassembly Guide*\n\n"
        "*Linux / Mac:*\n"
        f"`cat {base}\\.part\\* > {base}`\n\n"
        "*Windows CMD:*\n"
        f"`copy /b {base}\\.part\\* {base}`\n\n"
        "*Verify (Linux):*\n"
        f"`md5sum {base}`"
    )
