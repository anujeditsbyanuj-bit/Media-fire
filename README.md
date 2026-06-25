# Xylon Mediafire Bot — Setup Guide

## Replit Secrets (Environment Variables)
Replit ke "Secrets" tab mein yeh sab set karo:

| Key              | Value                          |
|------------------|-------------------------------|
| BOT_TOKEN        | @BotFather se mila token      |
| API_ID           | my.telegram.org se            |
| API_HASH         | my.telegram.org se            |
| OWNER_ID         | Apna Telegram numeric ID      |
| MONGO_URI        | MongoDB Atlas connection URI  |
| BOT_NAME         | Mediafire Bot (optional)      |
| ADMIN_NAME       | Admin (optional)              |
| CHANNEL_USERNAME | @YourChannel (optional)       |
| OWNER_USERNAME   | @YourUsername (optional)      |

## Replit Workflow Fix (Double Response Fix)
Replit mein sirf EK workflow hona chahiye jo `python bot.py` run kare.

Agar do workflow hain ya bot.py do baar run ho raha hai — woh band karo.
Workflow mein sirf yeh hona chahiye:
```
python bot.py
```

## Double Response Problem?
Yeh hota hai jab:
1. Replit mein purana `.session` file exist karta hai
2. Bot do baar start ho raha ho (2 workflows)

Fix: Bot restart karo — ab session file automatically delete hoti hai har start pe.

## Commands
- /start — Welcome
- /help — Help
- /profile — Apna profile
- /history — Download history
- /ping — Latency check
- /cancel — Download cancel
- /premium — Premium plans
- /redeem KEY — Key activate

## Admin Commands (Owner only)
- /stats — Bot stats
- /genkey DAYS [COUNT] — Key generate
- /listkeys [all] — Keys list
- /delkey KEY — Key delete
- /addpremium USER_ID [DAYS] — Premium do
- /revokepremium USER_ID — Premium hatao
- /ban USER_ID — Ban karo
- /unban USER_ID — Unban karo
- /broadcast MESSAGE — Sab ko message
- /users — User list
