"""
Ɉ Montana Telegram Bot Module v3.1

Telegram participation per MONTANA_TECHNICAL_SPECIFICATION.md §15.
"""

from montana.bot.telegram import MontanaBot, BotConfig
from montana.bot.challenges import TimeChallenge, ChallengeManager

__all__ = [
    "MontanaBot",
    "BotConfig",
    "TimeChallenge",
    "ChallengeManager",
]
