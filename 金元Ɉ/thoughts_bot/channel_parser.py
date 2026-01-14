#!/usr/bin/env python3
"""
Channel Parser for Montana
Парсер Telegram каналов для 金元Ɉ

Каналы:
- @mylifethoughts369 (мысли)
- @mylifeprogram369 (музыка)
"""

import os
import json
import asyncio
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

    def add_message(self, msg: ChannelMessage):
        self.messages[msg.id] = asdict(msg)

    def get_last_id(self) -> int:
        if not self.messages:
            return 0
        return max(self.messages.keys())

    def get_messages_count(self) -> int:
        return len(self.messages)


async def parse_channel(client: TelegramClient, channel_key: str, channel_username: str, limit: int = 100):
    """Parse messages from a channel."""
    print(f"\nParsing {channel_username}...")

    storage = ChannelStorage(channel_key)
    last_id = storage.get_last_id()

    try:
        entity = await client.get_entity(channel_username)
    except Exception as e:
        print(f"Error getting entity {channel_username}: {e}")
        return

    new_count = 0

    async for message in client.iter_messages(entity, limit=limit):
        if not isinstance(message, Message):
            continue

        if message.id <= last_id:
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
            date_utc=message.date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            text=message.text or "",
            has_media=has_media,
            media_type=media_type,
            views=message.views or 0,
            forwards=message.forwards or 0,
        )

        storage.add_message(msg)
        new_count += 1

        if new_count % 10 == 0:
            print(f"  Parsed {new_count} new messages...")

    storage.save()
    print(f"  Done: {new_count} new messages (total: {storage.get_messages_count()})")


async def main():
    """Main parser function."""
    if not API_ID or not API_HASH:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH required")
        print("Get them at https://my.telegram.org")
        print("\nAdd to .env file:")
        print("TELEGRAM_API_ID=<your_id>")
        print("TELEGRAM_API_HASH=<your_hash>")
        print("TELEGRAM_PHONE=<your_phone>")
        return

    client = TelegramClient(str(SESSION_FILE), int(API_ID), API_HASH)

    print("Montana Channel Parser")
    print("=" * 40)

    await client.start(phone=PHONE)

    if not await client.is_user_authorized():
        print("Authorization required. Run again and enter code.")
        return

    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username})")

    for key, username in CHANNELS.items():
        await parse_channel(client, key, username, limit=500)

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
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_to_markdown()
    else:
        asyncio.run(main())
