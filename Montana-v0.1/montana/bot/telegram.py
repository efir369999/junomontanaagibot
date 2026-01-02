"""
Ɉ Montana Telegram Bot v3.1

Telegram participation per MONTANA_TECHNICAL_SPECIFICATION.md §15.

Tier 3 participation through Telegram Mini App.
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any

from montana.constants import (
    HEARTBEAT_INTERVAL_MS,
    TELEGRAM_MIN_HEARTBEAT_INTERVAL_SEC,
)
from montana.core.types import Hash, HeartbeatSource, ParticipationTier
from montana.core.heartbeat import LightHeartbeat, create_light_heartbeat
from montana.bot.challenges import (
    TimeChallenge,
    ChallengeManager,
    ChallengeType,
    ChallengeResult,
    format_challenge_question,
    parse_time_response,
)

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Telegram bot configuration."""
    token: str
    node_endpoint: str = "http://localhost:19656"
    challenge_interval_sec: int = 300  # 5 minutes between challenges
    min_heartbeat_interval_sec: int = TELEGRAM_MIN_HEARTBEAT_INTERVAL_SEC


@dataclass
class TelegramUser:
    """Registered Telegram user."""
    user_id: int
    username: Optional[str] = None
    node_id: Optional[Hash] = None
    registered_at: float = field(default_factory=time.time)
    heartbeat_count: int = 0
    last_heartbeat: float = 0.0
    score: float = 0.0
    last_challenge: float = 0.0
    challenges_completed: int = 0

    @property
    def tier(self) -> ParticipationTier:
        return ParticipationTier.TIER_3  # Telegram users are always Tier 3

    @property
    def source(self) -> HeartbeatSource:
        return HeartbeatSource.TELEGRAM_USER


class MontanaBot:
    """
    Telegram bot for Montana participation.

    Features:
    - User registration
    - Time challenges (¿Qué hora es, Chico?)
    - Heartbeat submission
    - Balance checking
    - Score tracking
    """

    def __init__(self, config: BotConfig):
        self.config = config

        # Challenge manager
        self.challenges = ChallengeManager()

        # User storage
        self._users: Dict[int, TelegramUser] = {}

        # Bot state
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # Handlers (for telegram library integration)
        self._message_handlers: List[Callable] = []

    @property
    def user_count(self) -> int:
        return len(self._users)

    async def start(self):
        """Start the bot."""
        if self._running:
            return

        logger.info("Starting Montana Telegram Bot...")

        self._running = True

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._challenge_cleanup_loop()),
            asyncio.create_task(self._heartbeat_reminder_loop()),
        ]

        logger.info("Montana Telegram Bot started")

    async def stop(self):
        """Stop the bot."""
        if not self._running:
            return

        logger.info("Stopping Montana Telegram Bot...")

        self._running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

        logger.info("Montana Telegram Bot stopped")

    async def handle_start(self, user_id: int, username: Optional[str] = None) -> str:
        """
        Handle /start command.

        Registers new user or welcomes existing user.
        """
        if user_id in self._users:
            user = self._users[user_id]
            return (
                f"Welcome back, {username or 'friend'}! 👋\n\n"
                f"📊 Your stats:\n"
                f"• Heartbeats: {user.heartbeat_count}\n"
                f"• Score: {user.score:.2f}\n"
                f"• Challenges: {user.challenges_completed}\n\n"
                "Use /challenge to participate!"
            )

        # Register new user
        user = TelegramUser(
            user_id=user_id,
            username=username,
            node_id=Hash.zero(),  # Will be set on first heartbeat
        )
        self._users[user_id] = user

        logger.info(f"Registered new user: {user_id} ({username})")

        return (
            f"Welcome to Ɉ Montana, {username or 'friend'}! 🏔️\n\n"
            "You are now registered as a Tier 3 participant.\n\n"
            "**How it works:**\n"
            "1. Complete time challenges\n"
            "2. Earn heartbeats and score\n"
            "3. Participate in the network\n\n"
            "Use /challenge to start!\n"
            "Use /help for more commands."
        )

    async def handle_challenge(self, user_id: int) -> str:
        """
        Handle /challenge command.

        Creates a new time challenge for the user.
        """
        if user_id not in self._users:
            return "Please use /start to register first."

        user = self._users[user_id]

        # Check for existing pending challenge
        pending = self.challenges.get_pending_challenge(user_id)
        if pending:
            return format_challenge_question(pending)

        # Check cooldown
        elapsed = time.time() - user.last_challenge
        if elapsed < self.config.challenge_interval_sec:
            remaining = int(self.config.challenge_interval_sec - elapsed)
            return f"⏳ Please wait {remaining} seconds before the next challenge."

        # Create new challenge
        challenge = self.challenges.create_challenge(
            user_id=user_id,
            challenge_type=ChallengeType.CURRENT_TIME,
        )
        user.last_challenge = time.time()

        return format_challenge_question(challenge)

    async def handle_time_response(
        self,
        user_id: int,
        response: str,
    ) -> str:
        """
        Handle user's response to time challenge.

        Args:
            user_id: Telegram user ID
            response: User's time response

        Returns:
            Response message
        """
        if user_id not in self._users:
            return "Please use /start to register first."

        user = self._users[user_id]

        # Get pending challenge
        challenge = self.challenges.get_pending_challenge(user_id)
        if not challenge:
            return "No active challenge. Use /challenge to start one."

        # Parse response
        response_time_ms = parse_time_response(response)
        if response_time_ms is None:
            return (
                "❌ Invalid time format.\n\n"
                "Please reply with:\n"
                "• `HH:MM:SS` (e.g., 14:30:45)\n"
                "• Unix timestamp in ms"
            )

        # Check response
        result, precision_bonus = self.challenges.check_response(
            challenge.challenge_id,
            response_time_ms,
        )

        if result == ChallengeResult.CORRECT:
            # Update user stats
            user.heartbeat_count += 1
            user.challenges_completed += 1
            user.score += 1.0 + precision_bonus

            # Generate heartbeat
            await self._submit_heartbeat(user)

            precision_text = ""
            if precision_bonus > 0:
                precision_text = f"\n🎯 Precision bonus: +{precision_bonus:.2f}"

            return (
                f"✅ **Correct!**{precision_text}\n\n"
                f"Deviation: {challenge.precision_ms}ms\n"
                f"Score: {user.score:.2f}\n\n"
                "Your heartbeat has been recorded. 💓"
            )

        elif result == ChallengeResult.INCORRECT:
            return (
                f"❌ **Incorrect!**\n\n"
                f"Expected: {challenge.expected_time_ms}\n"
                f"Your answer: {response_time_ms}\n"
                f"Deviation: {challenge.precision_ms}ms\n\n"
                f"Attempts remaining: {3 - challenge.attempts}"
            )

        elif result == ChallengeResult.TIMEOUT:
            return "⏰ Challenge expired. Use /challenge for a new one."

        elif result == ChallengeResult.TOO_MANY_ATTEMPTS:
            return "❌ Too many attempts. Use /challenge for a new one."

        return "Unknown error. Please try again."

    async def handle_stats(self, user_id: int) -> str:
        """Handle /stats command."""
        if user_id not in self._users:
            return "Please use /start to register first."

        user = self._users[user_id]

        return (
            f"📊 **Your Statistics**\n\n"
            f"• User ID: {user_id}\n"
            f"• Tier: {user.tier.name}\n"
            f"• Heartbeats: {user.heartbeat_count}\n"
            f"• Score: {user.score:.2f}\n"
            f"• Challenges: {user.challenges_completed}\n"
            f"• Registered: {time.strftime('%Y-%m-%d', time.localtime(user.registered_at))}\n"
        )

    async def handle_help(self) -> str:
        """Handle /help command."""
        return (
            "🏔️ **Ɉ Montana Telegram Bot**\n\n"
            "**Commands:**\n"
            "/start - Register or check status\n"
            "/challenge - Start a time challenge\n"
            "/stats - View your statistics\n"
            "/leaderboard - Top participants\n"
            "/help - Show this help\n\n"
            "**How to participate:**\n"
            "1. Complete time challenges by answering\n"
            "   \"¿Qué hora es, Chico?\" with current UTC time\n"
            "2. More precision = more points\n"
            "3. Regular participation increases your score\n\n"
            "**Tier 3 Participation**\n"
            "As a Telegram user, you participate at Tier 3,\n"
            "eligible for 10% of block rewards."
        )

    async def handle_leaderboard(self) -> str:
        """Handle /leaderboard command."""
        # Sort users by score
        sorted_users = sorted(
            self._users.values(),
            key=lambda u: u.score,
            reverse=True
        )[:10]

        if not sorted_users:
            return "No participants yet. Be the first!"

        lines = ["🏆 **Top 10 Participants**\n"]
        for i, user in enumerate(sorted_users, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            name = user.username or f"User {user.user_id}"
            lines.append(f"{medal} {name}: {user.score:.2f}")

        return "\n".join(lines)

    async def _submit_heartbeat(self, user: TelegramUser):
        """Submit heartbeat for user."""
        # Create light heartbeat
        from montana.core.types import PublicKey
        from montana.crypto.sphincs import generate_sphincs_keypair

        # In production, user would have persistent keys
        # For now, generate ephemeral
        pk, sk = generate_sphincs_keypair()

        heartbeat = create_light_heartbeat(
            node_id=Hash(str(user.user_id).encode().ljust(32, b'\x00')[:32]),
            public_key=pk,
            prev_heartbeat_hash=Hash.zero(),
            source=HeartbeatSource.TELEGRAM_USER,
        )

        # In production, this would submit to a Full Node
        logger.debug(f"Heartbeat submitted for user {user.user_id}")

        user.last_heartbeat = time.time()

    async def _challenge_cleanup_loop(self):
        """Periodically clean up expired challenges."""
        while self._running:
            try:
                self.challenges.cleanup_expired()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Challenge cleanup error: {e}")
                await asyncio.sleep(60)

    async def _heartbeat_reminder_loop(self):
        """Send reminders for inactive users."""
        while self._running:
            try:
                now = time.time()
                for user in self._users.values():
                    if now - user.last_heartbeat > 3600:  # 1 hour
                        # Would send reminder via Telegram
                        pass

                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reminder loop error: {e}")
                await asyncio.sleep(300)

    def get_stats(self) -> Dict:
        """Get bot statistics."""
        return {
            "users": len(self._users),
            "total_heartbeats": sum(u.heartbeat_count for u in self._users.values()),
            "total_challenges": self.challenges.get_stats()["total_challenges"],
            "challenge_success_rate": self.challenges.get_stats()["success_rate"],
        }
