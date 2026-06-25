"""
database.py — MongoDB Atlas async storage via Motor
"""

import asyncio
import secrets
import string
from datetime import datetime, date, timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
import config

_client  = None
_db_obj  = None
_db_lock = asyncio.Lock()   # FIX A: double-init race condition prevent karo


async def _db():
    global _client, _db_obj
    # FIX A: Lock se ensure karo sirf ek coroutine init kare
    async with _db_lock:
        if _db_obj is None:
            _client = AsyncIOMotorClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
            _db_obj = _client[config.MONGO_DB]
            await _db_obj[config.MONGO_COL].create_index("uid", unique=True, background=True)
            await _db_obj["keys"].create_index("key", unique=True, background=True)
    return _db_obj


def _default_user(uid: int, name: str = "") -> dict:
    return {
        "uid":              uid,
        "name":             name,
        "is_premium":       False,
        "premium_expiry":   None,
        "is_banned":        False,
        "downloads_today":  0,
        "last_reset":       str(date.today()),
        "total_downloads":  0,
        "history":          [],
        "joined":           datetime.now().strftime("%d %b %Y"),
    }


def _is_premium_active(u: dict) -> bool:
    if not u.get("is_premium"):
        return False
    exp = u.get("premium_expiry")
    if exp is None:
        return True
    try:
        return datetime.fromisoformat(exp) > datetime.now()
    except (ValueError, TypeError):
        return False


async def get_user(uid: int, name: str = "") -> dict:
    db  = await _db()
    col = db[config.MONGO_COL]
    u   = await col.find_one({"uid": uid}, {"_id": 0})

    if not u:
        u = _default_user(uid, name)
        await col.insert_one(dict(u))
        return u

    if name and u.get("name") != name:
        await col.update_one({"uid": uid}, {"$set": {"name": name}})
        u["name"] = name

    if u.get("is_premium") and u.get("premium_expiry"):
        try:
            if datetime.fromisoformat(u["premium_expiry"]) <= datetime.now():
                await col.update_one(
                    {"uid": uid},
                    {"$set": {"is_premium": False, "premium_expiry": None}},
                )
                u["is_premium"]     = False
                u["premium_expiry"] = None
        except (ValueError, TypeError):
            await col.update_one({"uid": uid}, {"$set": {"premium_expiry": None}})
            u["premium_expiry"] = None

    today = str(date.today())
    if u.get("last_reset") != today:
        await col.update_one(
            {"uid": uid},
            {"$set": {"downloads_today": 0, "last_reset": today}},
        )
        u["downloads_today"] = 0
        u["last_reset"]      = today

    u.setdefault("history", [])
    u.setdefault("total_downloads", 0)
    u.setdefault("is_banned", False)
    u.setdefault("downloads_today", 0)

    return u


async def add_history(uid: int, filename: str, size_str: str):
    db    = await _db()
    entry = {
        "name": filename,
        "size": size_str,
        "date": datetime.now().strftime("%d %b %Y %H:%M"),
    }
    await db[config.MONGO_COL].update_one(
        {"uid": uid},
        {
            "$push": {"history": {"$each": [entry], "$position": 0, "$slice": 20}},
            "$inc":  {"downloads_today": 1, "total_downloads": 1},
        },
    )


async def get_all_users() -> list:
    db     = await _db()
    cursor = db[config.MONGO_COL].find({}, {"_id": 0})
    return await cursor.to_list(length=None)


async def set_premium(uid: int, value: bool, expiry: Optional[datetime] = None):
    """upsert=True — agar user DB mein nahi to bhi set ho jaata hai."""
    db  = await _db()
    upd = {
        "is_premium":     value,
        "premium_expiry": expiry.isoformat() if expiry else None,
    }
    default = _default_user(uid)
    default.update(upd)
    await db[config.MONGO_COL].update_one(
        {"uid": uid},
        {"$set": upd, "$setOnInsert": {k: v for k, v in default.items() if k not in upd}},
        upsert=True,
    )


async def set_banned(uid: int, value: bool):
    """upsert=True — agar user DB mein nahi to bhi ban ho jaata hai."""
    db      = await _db()
    default = _default_user(uid)
    default["is_banned"] = value
    await db[config.MONGO_COL].update_one(
        {"uid": uid},
        {
            "$set": {"is_banned": value},
            "$setOnInsert": {k: v for k, v in default.items() if k != "is_banned"},
        },
        upsert=True,
    )


async def get_stats() -> dict:
    db        = await _db()
    col       = db[config.MONGO_COL]
    today_str = str(date.today())
    now       = datetime.now().isoformat()

    total   = await col.count_documents({})
    premium = await col.count_documents({
        "is_premium": True,
        "$or": [
            {"premium_expiry": None},
            {"premium_expiry": {"$gt": now}},
        ],
    })
    banned  = await col.count_documents({"is_banned": True})
    active  = await col.count_documents({
        "last_reset":      today_str,
        "downloads_today": {"$gt": 0},
    })
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_downloads"}}}]
    res      = await col.aggregate(pipeline).to_list(1)
    total_dl = res[0]["total"] if res else 0

    return {
        "total_users":     total,
        "premium_users":   premium,
        "banned_users":    banned,
        "active_today":    active,
        "total_downloads": total_dl,
    }


def _make_key() -> str:
    chars = string.ascii_uppercase + string.digits
    part  = lambda n: "".join(secrets.choice(chars) for _ in range(n))
    return f"XYLON-{part(4)}-{part(4)}-{part(4)}"


async def create_key(days: int) -> str:
    db  = await _db()
    key = _make_key()
    doc = {
        "key":     key,
        "days":    days,
        "used":    False,
        "used_by": None,
        "used_at": None,
        "created": datetime.now().isoformat(),
    }
    await db["keys"].insert_one(doc)
    return key


async def redeem_key(key: str, uid: int) -> dict:
    """
    FIX B: TOCTOU race condition khatam — find_one_and_update atomic hai.
    Do users ek saath same key use nahi kar sakte.
    """
    db = await _db()

    # Atomic: sirf tab update karo jab used=False ho
    doc = await db["keys"].find_one_and_update(
        {"key": key, "used": False},
        {"$set": {"used": True, "used_by": uid, "used_at": datetime.now().isoformat()}},
        return_document=False,   # original doc return karo (before update)
    )

    if doc is None:
        # Key exist karta hai ya nahi — check karo
        existing = await db["keys"].find_one({"key": key})
        if not existing:
            return {"ok": False, "reason": "invalid"}
        # Key exist karta hai lekin already used hai
        if existing.get("used_by") == uid:
            return {"ok": False, "reason": "own"}
        return {"ok": False, "reason": "used"}

    days   = doc["days"]
    expiry = datetime.now() + timedelta(days=days)

    # Extend if already premium
    u = await db[config.MONGO_COL].find_one({"uid": uid})
    if u and u.get("is_premium") and u.get("premium_expiry"):
        try:
            current_exp = datetime.fromisoformat(u["premium_expiry"])
            if current_exp > datetime.now():
                expiry = current_exp + timedelta(days=days)
        except (ValueError, TypeError):
            pass

    await set_premium(uid, True, expiry)
    return {"ok": True, "days": days, "expiry": expiry}


async def list_keys(show_used: bool = False) -> list:
    db     = await _db()
    query  = {} if show_used else {"used": False}
    cursor = db["keys"].find(query, {"_id": 0})
    return await cursor.to_list(length=None)


async def delete_key(key: str) -> bool:
    db  = await _db()
    res = await db["keys"].delete_one({"key": key, "used": False})
    return res.deleted_count > 0


async def close():
    global _client, _db_obj
    if _client:
        _client.close()
        _client = None
        _db_obj = None
