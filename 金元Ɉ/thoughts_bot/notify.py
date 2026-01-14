#!/usr/bin/env python3
"""
Montana Network Notification Script
Третий слой бэкапа — уведомления в Telegram

Использование:
    python notify.py "Сообщение"
    python notify.py --sync "commit_hash"
    python notify.py --file "path/to/file"
"""

import os
import sys
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import telegram

BOT_TOKEN = os.getenv("THOUGHTS_BOT_TOKEN", "REDACTED_TOKEN_2")
ADMIN_USER_ID = 8552053404


async def send_notification(message: str, parse_mode: str = None):
    """Send notification to admin via Telegram bot."""
    bot = telegram.Bot(token=BOT_TOKEN)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    full_message = f"🔔 *Montana Network*\n{timestamp}\n\n{message}"

    try:
        await bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=full_message,
            parse_mode=parse_mode or "Markdown"
        )
        print(f"Notification sent: {message[:50]}...")
        return True
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False


async def notify_sync(commit_hash: str, server: str = "unknown"):
    """Notify about git sync."""
    message = f"📦 *Sync Complete*\n\n"
    message += f"Server: `{server}`\n"
    message += f"Commit: `{commit_hash[:8]}`"

    return await send_notification(message)


async def notify_file(filepath: str, action: str = "created"):
    """Notify about file operation."""
    path = Path(filepath)
    message = f"📄 *File {action}*\n\n"
    message += f"Path: `{path.name}`\n"
    message += f"Dir: `{path.parent}`"

    return await send_notification(message)


async def notify_channel_parsed(channel: str, count: int):
    """Notify about channel parsing."""
    message = f"📡 *Channel Parsed*\n\n"
    message += f"Channel: {channel}\n"
    message += f"Messages: {count}"

    return await send_notification(message)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python notify.py 'message'")
        print("  python notify.py --sync <commit>")
        print("  python notify.py --file <path>")
        print("  python notify.py --channel <name> <count>")
        return

    if sys.argv[1] == "--sync":
        commit = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        server = sys.argv[3] if len(sys.argv) > 3 else "network"
        asyncio.run(notify_sync(commit, server))

    elif sys.argv[1] == "--file":
        filepath = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        action = sys.argv[3] if len(sys.argv) > 3 else "created"
        asyncio.run(notify_file(filepath, action))

    elif sys.argv[1] == "--channel":
        channel = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        asyncio.run(notify_channel_parsed(channel, count))

    else:
        message = " ".join(sys.argv[1:])
        asyncio.run(send_notification(message))


if __name__ == "__main__":
    main()
