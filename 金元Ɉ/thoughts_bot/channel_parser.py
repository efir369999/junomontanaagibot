#!/usr/bin/env python3
"""
Channel Parser for Montana — Потоковый парсер
Парсер Telegram каналов для 金元Ɉ

Каналы:
- @mylifethoughts369 (мысли)
- @mylifeprogram369 (музыка)

Genesis: 12 января 2026
Режим: потоковая синхронизация с сетью
"""

import os
import sys
import json
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

# Configuration
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")

# Genesis date - парсим с этой даты
GENESIS_DATE = datetime(2026, 1, 12, 0, 0, 0, tzinfo=timezone.utc)

# Stream mode interval (seconds)
STREAM_INTERVAL = 60

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHANNELS_DIR = DATA_DIR / "channels"
SESSION_FILE = BASE_DIR / "montana_parser.session"

CHANNELS_DIR.mkdir(parents=True, exist_ok=True)

# Channels to parse
CHANNELS = {
    "thoughts": "@mylifethoughts369",
    "music": "@mylifeprogram369",
}


def get_credentials():
    """Get API credentials from env or prompt."""
    api_id = API_ID or os.getenv("TELEGRAM_API_ID")
    api_hash = API_HASH or os.getenv("TELEGRAM_API_HASH")

    if api_id and api_hash:
        return int(api_id), api_hash

    print("\nTelegram API credentials required")
    print("1. Go to https://my.telegram.org")
    print("2. Log in with your phone")
    print("3. Go to 'API development tools'")
    print("4. Create an app (any name)")
    print("5. Copy api_id and api_hash")
    print()

    api_id = input("api_id (number): ").strip()
    api_hash = input("api_hash (string): ").strip()

    if not api_id or not api_hash:
        return None, None

    return int(api_id), api_hash


@dataclass
class ChannelMessage:
    """Parsed channel message."""
    id: int
    channel: str
    date: str
    date_utc: str
    text: str
    has_media: bool
    media_type: Optional[str]
    views: int
    forwards: int


class ChannelStorage:
    """Storage for parsed channel messages."""

    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.file = CHANNELS_DIR / f"{channel_name}.json"
        self.messages: dict[int, dict] = {}
        self._load()

    def _load(self):
        if self.file.exists():
            try:
                data = json.loads(self.file.read_text(encoding="utf-8"))
                self.messages = {int(k): v for k, v in data.get("messages", {}).items()}
            except Exception as e:
                print(f"Error loading {self.file}: {e}")

    def save(self):
        data = {
            "channel": self.channel_name,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "message_count": len(self.messages),
            "messages": self.messages,
        }
        self.file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_message(self, msg: ChannelMessage) -> bool:
        """Add message, return True if new."""
        if msg.id in self.messages:
            return False
        self.messages[msg.id] = asdict(msg)
        return True

    def get_last_id(self) -> int:
        if not self.messages:
            return 0
        return max(self.messages.keys())

    def get_messages_count(self) -> int:
        return len(self.messages)


def sync_to_network():
    """Sync data to Montana network (Moscow ↔ Amsterdam)."""
    try:
        # Git add and commit
        result = subprocess.run(
            ["git", "add", str(CHANNELS_DIR)],
            cwd=str(BASE_DIR.parent.parent),
            capture_output=True,
            text=True
        )

        # Check if there are changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR.parent.parent),
            capture_output=True,
            text=True
        )

        if not status.stdout.strip():
            return False  # No changes

        # Commit
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(
            ["git", "commit", "-m", f"SYNC: Channel data {timestamp}"],
            cwd=str(BASE_DIR.parent.parent),
            capture_output=True
        )

        # Push to origin (backup)
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(BASE_DIR.parent.parent),
            capture_output=True
        )

        print(f"  Network sync: {timestamp}")
        return True

    except Exception as e:
        print(f"  Sync error: {e}")
        return False


async def parse_channel(client: TelegramClient, channel_key: str, channel_username: str, limit: int = 100) -> int:
    """Parse messages from a channel. Returns count of new messages."""
    storage = ChannelStorage(channel_key)

    try:
        entity = await client.get_entity(channel_username)
    except Exception as e:
        print(f"  Error getting {channel_username}: {e}")
        return 0

    new_count = 0

    async for message in client.iter_messages(entity, limit=limit):
        if not isinstance(message, Message):
            continue

        # Skip messages before genesis
        msg_date = message.date.astimezone(timezone.utc)
        if msg_date < GENESIS_DATE:
            continue

        media_type = None
        has_media = False

        if message.media:
            has_media = True
            if isinstance(message.media, MessageMediaPhoto):
                media_type = "photo"
            elif isinstance(message.media, MessageMediaDocument):
                doc = message.media.document
                if doc:
                    for attr in doc.attributes:
                        if hasattr(attr, "file_name"):
                            if attr.file_name.endswith((".mp3", ".ogg", ".wav", ".flac")):
                                media_type = "audio"
                            elif attr.file_name.endswith((".mp4", ".webm", ".mov")):
                                media_type = "video"
                            else:
                                media_type = "document"
                            break
                    if not media_type:
                        media_type = "document"

        msg = ChannelMessage(
            id=message.id,
            channel=channel_username,
            date=message.date.strftime("%Y-%m-%d %H:%M:%S"),
            date_utc=msg_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
            text=message.text or "",
            has_media=has_media,
            media_type=media_type,
            views=message.views or 0,
            forwards=message.forwards or 0,
        )

        if storage.add_message(msg):
            new_count += 1

    if new_count > 0:
        storage.save()

    return new_count


async def stream_mode(client: TelegramClient):
    """Continuous stream mode - постоянная синхронизация."""
    print("\n" + "=" * 50)
    print("STREAM MODE — постоянная синхронизация")
    print(f"Interval: {STREAM_INTERVAL}s")
    print("Press Ctrl+C to stop")
    print("=" * 50 + "\n")

    cycle = 0
    while True:
        cycle += 1
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        print(f"\n[{cycle}] {timestamp}")

        total_new = 0
        for key, username in CHANNELS.items():
            new_count = await parse_channel(client, key, username, limit=50)
            if new_count > 0:
                print(f"  {key}: +{new_count}")
                total_new += new_count

        if total_new > 0:
            sync_to_network()

        await asyncio.sleep(STREAM_INTERVAL)


async def main():
    """Main parser function."""
    api_id, api_hash = get_credentials()

    if not api_id or not api_hash:
        print("Error: Credentials required")
        return

    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)

    print("\n" + "=" * 50)
    print("Montana Channel Parser")
    print(f"Genesis: {GENESIS_DATE.strftime('%Y-%m-%d')}")
    print("=" * 50)

    await client.start(phone=PHONE)

    if not await client.is_user_authorized():
        print("Authorization required. Run again and enter code.")
        return

    me = await client.get_me()
    print(f"Authorized: {me.first_name} (@{me.username})")

    # Check for stream mode
    if "--stream" in sys.argv:
        try:
            await stream_mode(client)
        except KeyboardInterrupt:
            print("\n\nStopping stream...")
    else:
        # One-time parse
        print("\nParsing channels...")
        for key, username in CHANNELS.items():
            print(f"\n{key}: {username}")
            new_count = await parse_channel(client, key, username, limit=1000)
            storage = ChannelStorage(key)
            print(f"  New: {new_count}, Total: {storage.get_messages_count()}")

        sync_to_network()

    await client.disconnect()
    print("\nDone.")


def export_to_markdown():
    """Export parsed messages to markdown files."""
    print("\nExporting to markdown...")

    export_dir = BASE_DIR / "parsed" / "channels"
    export_dir.mkdir(parents=True, exist_ok=True)

    for channel_key in CHANNELS.keys():
        storage = ChannelStorage(channel_key)

        if not storage.messages:
            print(f"  {channel_key}: no messages")
            continue

        sorted_msgs = sorted(storage.messages.values(), key=lambda x: x["id"])

        md_content = f"# {CHANNELS[channel_key]}\n\n"
        md_content += f"**Total messages:** {len(sorted_msgs)}\n"
        md_content += f"**Genesis:** {GENESIS_DATE.strftime('%Y-%m-%d')}\n"
        md_content += f"**Last updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        md_content += "---\n\n"

        for msg in sorted_msgs:
            md_content += f"## [{msg['id']}] {msg['date_utc']}\n\n"

            if msg["text"]:
                md_content += f"{msg['text']}\n\n"

            if msg["has_media"]:
                md_content += f"*[{msg['media_type'] or 'media'}]*\n\n"

            if msg["views"] > 0:
                md_content += f"Views: {msg['views']}"
                if msg["forwards"] > 0:
                    md_content += f" | Forwards: {msg['forwards']}"
                md_content += "\n\n"

            md_content += "---\n\n"

        output_file = export_dir / f"{channel_key}.md"
        output_file.write_text(md_content, encoding="utf-8")
        print(f"  {channel_key}: {len(sorted_msgs)} messages -> {output_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_to_markdown()
    else:
        asyncio.run(main())
