"""
Ɉ Montana Time Challenges v3.1

Time challenges for Telegram participation per MONTANA_TECHNICAL_SPECIFICATION.md §15.2-15.3.

"¿Qué hora es, Chico?" — Time challenge for temporal verification.
"""

from __future__ import annotations
import secrets
import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum, auto

from montana.constants import (
    CHALLENGE_TIMEOUT_SEC,
    CHALLENGE_PRECISION_BONUS_THRESHOLD_MS,
    MAX_CHALLENGE_ATTEMPTS,
)
from montana.core.types import Hash

import logging
logger = logging.getLogger(__name__)


class ChallengeType(IntEnum):
    """Type of time challenge."""
    CURRENT_TIME = 1      # "What time is it?"
    TIME_ZONE = 2         # "What time is it in Tokyo?"
    FUTURE_TIME = 3       # "What time will it be in 5 minutes?"
    ELAPSED_TIME = 4      # "How long since the last block?"


class ChallengeResult(IntEnum):
    """Result of challenge response."""
    PENDING = 0
    CORRECT = 1
    INCORRECT = 2
    TIMEOUT = 3
    TOO_MANY_ATTEMPTS = 4


@dataclass
class TimeChallenge:
    """
    A time challenge for verification.

    Per §15.3: "¿Qué hora es, Chico?"

    Users must respond with current UTC time within tolerance.
    Precision is rewarded with bonus score.
    """
    challenge_id: str
    user_id: int                          # Telegram user ID
    challenge_type: ChallengeType
    created_at: float = field(default_factory=time.time)
    expected_time_ms: int = 0             # Expected answer (UTC ms)
    tolerance_ms: int = 5000              # Allowed deviation (5 sec default)
    expires_at: float = 0.0
    attempts: int = 0
    result: ChallengeResult = ChallengeResult.PENDING
    response_time_ms: Optional[int] = None
    precision_ms: Optional[int] = None    # How close to expected
    precision_bonus: float = 0.0

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + CHALLENGE_TIMEOUT_SEC

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.result == ChallengeResult.PENDING and not self.is_expired

    def check_response(self, response_time_ms: int) -> ChallengeResult:
        """
        Check user's response.

        Args:
            response_time_ms: User's answer (UTC timestamp in ms)

        Returns:
            Challenge result
        """
        self.attempts += 1
        self.response_time_ms = response_time_ms

        if self.is_expired:
            self.result = ChallengeResult.TIMEOUT
            return self.result

        if self.attempts > MAX_CHALLENGE_ATTEMPTS:
            self.result = ChallengeResult.TOO_MANY_ATTEMPTS
            return self.result

        # Calculate deviation
        deviation = abs(response_time_ms - self.expected_time_ms)
        self.precision_ms = deviation

        if deviation <= self.tolerance_ms:
            self.result = ChallengeResult.CORRECT

            # Calculate precision bonus
            if deviation < CHALLENGE_PRECISION_BONUS_THRESHOLD_MS:
                # Bonus for sub-second precision
                self.precision_bonus = 1.0 - (deviation / CHALLENGE_PRECISION_BONUS_THRESHOLD_MS)
                logger.debug(f"Precision bonus: {self.precision_bonus:.2f} for {deviation}ms deviation")
        else:
            self.result = ChallengeResult.INCORRECT

        return self.result


class ChallengeManager:
    """
    Manages time challenges for Telegram users.

    Handles:
    - Challenge generation
    - Response validation
    - Score calculation
    - Rate limiting
    """

    def __init__(
        self,
    ):

        # Active challenges
        self._challenges: Dict[str, TimeChallenge] = {}
        self._user_challenges: Dict[int, List[str]] = {}  # user_id -> challenge_ids

        # Stats
        self._total_challenges = 0
        self._correct_responses = 0

    def create_challenge(
        self,
        user_id: int,
        challenge_type: ChallengeType = ChallengeType.CURRENT_TIME,
        tolerance_ms: int = 5000,
    ) -> TimeChallenge:
        """
        Create a new time challenge.

        Args:
            user_id: Telegram user ID
            challenge_type: Type of challenge
            tolerance_ms: Allowed deviation

        Returns:
            New TimeChallenge
        """
        challenge_id = secrets.token_hex(16)

        # Expected answer: current UTC time in milliseconds
        expected_time_ms = int(time.time() * 1000)

        challenge = TimeChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            challenge_type=challenge_type,
            expected_time_ms=expected_time_ms,
            tolerance_ms=tolerance_ms,
        )

        # Store challenge
        self._challenges[challenge_id] = challenge

        if user_id not in self._user_challenges:
            self._user_challenges[user_id] = []
        self._user_challenges[user_id].append(challenge_id)

        self._total_challenges += 1

        logger.debug(f"Created challenge {challenge_id[:16]} for user {user_id}")

        return challenge

    def check_response(
        self,
        challenge_id: str,
        response_time_ms: int,
    ) -> Tuple[ChallengeResult, float]:
        """
        Check user's response to challenge.

        Args:
            challenge_id: Challenge ID
            response_time_ms: User's answer

        Returns:
            (result, precision_bonus)
        """
        if challenge_id not in self._challenges:
            return ChallengeResult.INCORRECT, 0.0

        challenge = self._challenges[challenge_id]
        result = challenge.check_response(response_time_ms)

        if result == ChallengeResult.CORRECT:
            self._correct_responses += 1

        return result, challenge.precision_bonus

    def get_challenge(self, challenge_id: str) -> Optional[TimeChallenge]:
        """Get challenge by ID."""
        return self._challenges.get(challenge_id)

    def get_user_challenges(self, user_id: int) -> List[TimeChallenge]:
        """Get all challenges for user."""
        if user_id not in self._user_challenges:
            return []

        return [
            self._challenges[cid]
            for cid in self._user_challenges[user_id]
            if cid in self._challenges
        ]

    def get_pending_challenge(self, user_id: int) -> Optional[TimeChallenge]:
        """Get pending challenge for user."""
        for challenge in self.get_user_challenges(user_id):
            if challenge.is_pending:
                return challenge
        return None

    def cleanup_expired(self):
        """Remove expired challenges."""
        expired = [
            cid for cid, c in self._challenges.items()
            if c.is_expired and c.result == ChallengeResult.PENDING
        ]

        for cid in expired:
            challenge = self._challenges.pop(cid)
            challenge.result = ChallengeResult.TIMEOUT

        if expired:
            logger.debug(f"Cleaned {len(expired)} expired challenges")

    def get_stats(self) -> Dict:
        """Get challenge statistics."""
        return {
            "total_challenges": self._total_challenges,
            "correct_responses": self._correct_responses,
            "success_rate": (
                self._correct_responses / self._total_challenges
                if self._total_challenges > 0 else 0.0
            ),
            "active_challenges": len([
                c for c in self._challenges.values()
                if c.is_pending
            ]),
        }


def format_challenge_question(challenge: TimeChallenge) -> str:
    """
    Format challenge as question text.

    Returns Telegram-friendly message.
    """
    if challenge.challenge_type == ChallengeType.CURRENT_TIME:
        return (
            "🕐 **¿Qué hora es, Chico?**\n\n"
            "Reply with the current UTC time in format:\n"
            "`HH:MM:SS` or Unix timestamp in milliseconds\n\n"
            f"⏱ Time remaining: {int(challenge.expires_at - time.time())}s"
        )

    elif challenge.challenge_type == ChallengeType.TIME_ZONE:
        return (
            "🌍 **Time Zone Challenge**\n\n"
            "What is the current UTC time?\n"
            "Reply with: `HH:MM:SS`\n\n"
            f"⏱ Time remaining: {int(challenge.expires_at - time.time())}s"
        )

    return "Unknown challenge type"


def parse_time_response(response: str) -> Optional[int]:
    """
    Parse user's time response.

    Accepts:
    - HH:MM:SS format
    - Unix timestamp (seconds or milliseconds)

    Returns:
        Unix timestamp in milliseconds, or None if invalid
    """
    response = response.strip()

    # Try parsing as Unix timestamp
    try:
        ts = int(response)
        # If it looks like seconds (10 digits), convert to ms
        if ts < 10_000_000_000:
            ts *= 1000
        return ts
    except ValueError:
        pass

    # Try parsing as HH:MM:SS
    try:
        parts = response.split(":")
        if len(parts) >= 2:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) > 2 else 0

            # Get current UTC date
            import datetime
            now = datetime.datetime.utcnow()
            target = now.replace(
                hour=hours,
                minute=minutes,
                second=seconds,
                microsecond=0
            )

            return int(target.timestamp() * 1000)
    except (ValueError, IndexError):
        pass

    return None
