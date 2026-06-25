"""
mediafire_dl.py — Async Mediafire resolver + downloader
"""

import re
import asyncio
import aiohttp
import aiofiles
from typing import Callable, Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FILE_API   = "https://www.mediafire.com/api/1.5/file/get_info.php?quick_key={key}&response_format=json"
LINKS_API  = "https://www.mediafire.com/api/1.5/file/get_links.php?quick_key={key}&link_type=normal_download&response_format=json"
FOLDER_API = "https://www.mediafire.com/api/1.5/folder/get_content.php?folder_key={key}&content_type={ctype}&chunk_size=100&chunk={chunk}&response_format=json"

MAX_RETRIES   = 4
RETRY_DELAY   = 2
CHUNK_SIZE    = 524288   # 512 KB
# FIX #3: recursion limit — max folder depth
MAX_FOLDER_DEPTH = 10

TIMEOUT_SHORT = aiohttp.ClientTimeout(total=60,   connect=15)
TIMEOUT_DL    = aiohttp.ClientTimeout(total=None, connect=15)


def is_folder_link(url: str) -> bool:
    return bool(re.search(r"mediafire\.com/folder/", url, re.I))


def extract_folder_key(url: str) -> str:
    m = re.search(r"mediafire\.com/folder/([a-zA-Z0-9]+)", url, re.I)
    if m:
        return m.group(1)
    h = re.search(r"#([a-zA-Z0-9]+)", url)
    return h.group(1) if h else ""


def extract_file_key(url: str) -> str:
    m = re.search(r"mediafire\.com/file/([a-zA-Z0-9]+)", url, re.I)
    return m.group(1) if m else ""


async def _fetch(session: aiohttp.ClientSession, url: str, timeout=None, **kwargs):
    last_exc = Exception("Unknown error")
    t = timeout or TIMEOUT_SHORT
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await session.get(url, timeout=t, allow_redirects=True, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
    raise last_exc


async def get_info(url: str) -> Optional[dict]:
    """
    Resolve a Mediafire file URL.
    Returns: {'name': str, 'size': int, 'url': str, 'key': str} or None
    """
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        key = extract_file_key(url)

        if key:
            try:
                async with await _fetch(session, FILE_API.format(key=key)) as r:
                    data = await r.json(content_type=None)

                if data.get("response", {}).get("result") == "Success":
                    fi = data["response"]["file_info"]

                    async with await _fetch(session, LINKS_API.format(key=key)) as lr:
                        ldata = await lr.json(content_type=None)

                    links  = ldata.get("response", {}).get("links", [])
                    dl_url = ""
                    if isinstance(links, list) and links:
                        dl_url = links[0].get("normal_download", "")

                    return {
                        "name": fi.get("filename", "file"),
                        "size": _parse_size(fi.get("size", "0")),
                        "url":  dl_url or url,
                        "key":  key,
                    }
            except Exception:
                pass  # fall through to HTML scraping

        # HTML scraping fallback
        try:
            async with await _fetch(session, url) as resp:
                html = await resp.text()
        except Exception as e:
            raise Exception(f"Could not fetch page: {e}")

        dl_match = (
            re.search(r'"(https://download\d+\.mediafire\.com/[^"]+?)"', html)
            or re.search(r"(https://download\d+\.mediafire\.com/[^\s\"'<>]+)", html)
        )
        if not dl_match:
            return None

        dl_url = dl_match.group(1)

        name_match = (
            re.search(r'id="downloadButton"[^>]*>\s*([^<]+?)\s*<', html)
            or re.search(r'"filename"\s*:\s*"([^"]+)"', html)
            or re.search(r'<title>([^<]+?)\s*[-|]', html)
        )
        filename = (
            name_match.group(1).strip()
            if name_match
            else (url.rstrip("/").split("/")[-1] or "file")
        )
        filename = filename.strip(" \t\n\r")

        size = 0
        sz = re.search(r'"fileSize"\s*:\s*"?(\d+)"?', html)
        if sz:
            size = int(sz.group(1))
        else:
            sz = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB)', html, re.I)
            if sz:
                size = _human_to_bytes(float(sz.group(1)), sz.group(2).upper())

        return {"name": filename, "size": size, "url": dl_url, "key": key}


async def get_folder_files(folder_key: str) -> list:
    files = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # FIX #3: depth=0 se shuru, MAX_FOLDER_DEPTH tak allowed
        await _collect_files(session, folder_key, files, depth=0)
    return files


async def _collect_files(session, folder_key: str, result: list, depth: int = 0):
    """
    FIX #3: depth limit add kiya — infinite recursion se protect karta hai.
    Deeply nested folders (>10 levels) skip ho jaate hain.
    """
    if depth > MAX_FOLDER_DEPTH:
        return  # Too deep — skip silently

    # Files (paginated)
    chunk = 1
    while True:
        url = FOLDER_API.format(key=folder_key, ctype="files", chunk=chunk)
        try:
            async with await _fetch(session, url) as r:
                data = await r.json(content_type=None)
        except Exception:
            break

        fc = data.get("response", {}).get("folder_content", {})
        for f in fc.get("files") or []:
            # FIX #9: page_url empty hone par quickkey se fallback URL banao
            file_key  = f.get("quickkey", "")
            page_url  = (f.get("links") or {}).get("normal_download", "")
            if not page_url and file_key:
                page_url = f"https://www.mediafire.com/file/{file_key}"

            result.append({
                "name":     f.get("filename", "file"),
                "size":     _parse_size(f.get("size", "0")),
                "page_url": page_url,
                "key":      file_key,
            })

        if fc.get("more_chunks") == "yes":
            chunk += 1
        else:
            break

    # Subfolders — depth + 1 pass karo
    sub_chunk = 1
    while True:
        url = FOLDER_API.format(key=folder_key, ctype="folders", chunk=sub_chunk)
        try:
            async with await _fetch(session, url) as r:
                data = await r.json(content_type=None)
        except Exception:
            break

        fc = data.get("response", {}).get("folder_content", {})
        for sf in fc.get("folders") or []:
            sub_key = sf.get("folderkey", "")
            if sub_key:
                # FIX #3: depth + 1 pass karo recursion mein
                await _collect_files(session, sub_key, result, depth=depth + 1)

        if fc.get("more_chunks") == "yes":
            sub_chunk += 1
        else:
            break


async def download(
    url: str,
    dest: str,
    progress_cb: Optional[Callable] = None,
    cancel_check: Optional[Callable] = None,
    chunk: int = CHUNK_SIZE,
):
    """
    Stream-download url → dest file.
    TIMEOUT_DL (no total timeout) — large files ke liye.
    """
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with await _fetch(session, url, timeout=TIMEOUT_DL) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0

            async with aiofiles.open(dest, "wb") as f:
                async for data in resp.content.iter_chunked(chunk):
                    if cancel_check and cancel_check():
                        raise asyncio.CancelledError("User cancelled")
                    await f.write(data)
                    done += len(data)
                    if progress_cb:
                        await progress_cb(done, total)


def _parse_size(val) -> int:
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _human_to_bytes(n: float, unit: str) -> int:
    mul = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(n * mul.get(unit, 1))
