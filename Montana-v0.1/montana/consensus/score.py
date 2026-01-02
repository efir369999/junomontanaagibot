"""
Ɉ Montana Score System v3.1

Participation scoring per MONTANA_TECHNICAL_SPECIFICATION.md §8.

Score = sqrt(heartbeats)

Score determines lottery weight and distribution eligibility.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

from montana.constants import (
    SCORE_PRECISION,
    SCORE_MIN_HEARTBEATS,
    ACTIVITY_WINDOW_BLOCKS,
    INACTIVITY_PENALTY_RATE,
)
from montana.core.types import Hash, ParticipationTier


@dataclass
class NodeScore:
    """
    Score state for a participant.

    Score is calculated as sqrt(heartbeats) with precision scaling.
    """
    node_id: Hash
    tier: ParticipationTier
    heartbeat_count: int = 0          # Total heartbeats
    last_heartbeat_height: int = 0    # Height of last heartbeat
    raw_score: int = 0                # Score with precision
    penalties: int = 0                # Accumulated penalties

    @property
    def effective_score(self) -> int:
        """Get score after penalties."""
        return max(0, self.raw_score - self.penalties)

    @property
    def score_float(self) -> float:
        """Get score as float."""
        return self.effective_score / SCORE_PRECISION

    def add_heartbeat(self, height: int) -> int:
        """
        Add heartbeat and update score.

        Returns:
            New score value
        """
        self.heartbeat_count += 1
        self.last_heartbeat_height = height
        self.raw_score = compute_score(self.heartbeat_count)
        return self.raw_score

    def apply_inactivity_penalty(self, current_height: int) -> int:
        """
        Apply penalty for inactivity.

        Called periodically to penalize inactive nodes.

        Returns:
            Penalty amount applied
        """
        if self.last_heartbeat_height == 0:
            return 0

        blocks_inactive = current_height - self.last_heartbeat_height

        if blocks_inactive <= ACTIVITY_WINDOW_BLOCKS:
            return 0

        # Penalty proportional to inactivity duration
        penalty = int(
            self.raw_score *
            INACTIVITY_PENALTY_RATE *
            (blocks_inactive - ACTIVITY_WINDOW_BLOCKS)
        )

        self.penalties += penalty
        return penalty


def compute_score(heartbeat_count: int) -> int:
    """
    Compute score from heartbeat count.

    Score = sqrt(heartbeats) * PRECISION

    Args:
        heartbeat_count: Number of valid heartbeats

    Returns:
        Score with precision scaling
    """
    if heartbeat_count < SCORE_MIN_HEARTBEATS:
        return 0

    sqrt_val = math.sqrt(heartbeat_count)
    return int(sqrt_val * SCORE_PRECISION)


def compute_score_float(heartbeat_count: int) -> float:
    """
    Compute score as float.

    Args:
        heartbeat_count: Number of valid heartbeats

    Returns:
        Score as float
    """
    if heartbeat_count < SCORE_MIN_HEARTBEATS:
        return 0.0

    return math.sqrt(heartbeat_count)


class ScoreTracker:
    """
    Tracks scores for all participants.
    """

    def __init__(self):
        self._scores: Dict[Hash, NodeScore] = {}
        self._total_score: int = 0
        self._tier_scores: Dict[ParticipationTier, int] = {
            ParticipationTier.TIER_1: 0,
            ParticipationTier.TIER_2: 0,
            ParticipationTier.TIER_3: 0,
        }

    def get_score(self, node_id: Hash) -> Optional[NodeScore]:
        """Get score for a node."""
        return self._scores.get(node_id)

    def get_or_create(
        self,
        node_id: Hash,
        tier: ParticipationTier,
    ) -> NodeScore:
        """Get or create score for a node."""
        if node_id not in self._scores:
            self._scores[node_id] = NodeScore(node_id=node_id, tier=tier)
        return self._scores[node_id]

    def add_heartbeat(
        self,
        node_id: Hash,
        tier: ParticipationTier,
        height: int,
    ) -> int:
        """
        Record heartbeat and update score.

        Returns:
            New score value
        """
        score = self.get_or_create(node_id, tier)
        old_score = score.effective_score

        score.add_heartbeat(height)
        new_score = score.effective_score

        # Update totals
        delta = new_score - old_score
        self._total_score += delta
        self._tier_scores[tier] += delta

        return new_score

    def apply_penalties(self, current_height: int) -> int:
        """
        Apply inactivity penalties to all nodes.

        Returns:
            Total penalty applied
        """
        total_penalty = 0

        for score in self._scores.values():
            penalty = score.apply_inactivity_penalty(current_height)
            if penalty > 0:
                total_penalty += penalty
                self._total_score -= penalty
                self._tier_scores[score.tier] -= penalty

        return total_penalty

    @property
    def total_score(self) -> int:
        """Get total score across all nodes."""
        return self._total_score

    def get_tier_score(self, tier: ParticipationTier) -> int:
        """Get total score for a tier."""
        return self._tier_scores.get(tier, 0)

    def get_top_scores(self, n: int = 10) -> list:
        """Get top N scores."""
        sorted_scores = sorted(
            self._scores.values(),
            key=lambda s: s.effective_score,
            reverse=True,
        )
        return sorted_scores[:n]

    def get_node_count(self) -> int:
        """Get number of tracked nodes."""
        return len(self._scores)

    def get_active_count(self, current_height: int) -> int:
        """Get number of active nodes (within activity window)."""
        return sum(
            1 for s in self._scores.values()
            if current_height - s.last_heartbeat_height <= ACTIVITY_WINDOW_BLOCKS
        )
