"""
Ɉ Montana Mempool v3.1

Transaction mempool with privacy tier sorting per MONTANA_TECHNICAL_SPECIFICATION.md §23.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from heapq import heappush, heappop

from montana.constants import (
    MAX_MEMPOOL_SIZE,
    MAX_MEMPOOL_TX_AGE_SEC,
    MIN_TRANSACTION_FEE,
    PRIVACY_T0_FEE_MULTIPLIER,
    PRIVACY_T1_FEE_MULTIPLIER,
    PRIVACY_T2_FEE_MULTIPLIER,
    PRIVACY_T3_FEE_MULTIPLIER,
)
from montana.core.types import Hash, PrivacyTier

logger = logging.getLogger(__name__)


@dataclass
class MempoolEntry:
    """
    Entry in the mempool.

    Sorted by:
    1. Privacy tier (higher tiers first for anonymity set)
    2. Fee rate (higher fees first)
    3. Time (older first)
    """
    tx_hash: Hash
    tx_data: bytes
    privacy_tier: PrivacyTier
    fee: int
    size: int
    added_time: float = field(default_factory=time.time)

    @property
    def fee_rate(self) -> float:
        """Fee per byte."""
        return self.fee / max(1, self.size)

    @property
    def priority(self) -> Tuple[int, float, float]:
        """
        Priority for sorting.

        Higher values = higher priority.
        Tuple: (tier priority, fee rate, negative time for FIFO on ties)
        """
        # Higher privacy tiers get priority for anonymity set building
        tier_priority = {
            PrivacyTier.T3_RING: 4,
            PrivacyTier.T2_CONFIDENTIAL: 3,
            PrivacyTier.T1_STEALTH: 2,
            PrivacyTier.T0_TRANSPARENT: 1,
        }
        return (
            tier_priority.get(self.privacy_tier, 0),
            self.fee_rate,
            -self.added_time,  # Negative so older is higher priority
        )

    def __lt__(self, other: "MempoolEntry") -> bool:
        # Reverse comparison for max-heap behavior
        return self.priority > other.priority

    def serialize(self) -> bytes:
        """Return transaction data."""
        return self.tx_data


class Mempool:
    """
    Transaction mempool with privacy tier awareness.

    Features:
    - Priority sorting by tier and fee
    - Duplicate detection
    - Expiration handling
    - Size limits
    """

    def __init__(
        self,
        max_size: int = MAX_MEMPOOL_SIZE,
        max_age_sec: float = MAX_MEMPOOL_TX_AGE_SEC,
    ):
        self.max_size = max_size
        self.max_age_sec = max_age_sec

        # Storage
        self._entries: Dict[Hash, MempoolEntry] = {}
        self._priority_queue: List[MempoolEntry] = []
        self._by_sender: Dict[Hash, Set[Hash]] = {}  # sender -> tx hashes

    @property
    def size(self) -> int:
        """Number of transactions in mempool."""
        return len(self._entries)

    @property
    def total_bytes(self) -> int:
        """Total size of all transactions."""
        return sum(e.size for e in self._entries.values())

    def add(
        self,
        tx_hash: Hash,
        tx_data: bytes,
        privacy_tier: PrivacyTier,
        fee: int,
        sender: Optional[Hash] = None,
    ) -> Tuple[bool, str]:
        """
        Add transaction to mempool.

        Args:
            tx_hash: Transaction hash
            tx_data: Serialized transaction
            privacy_tier: Privacy tier of transaction
            fee: Transaction fee
            sender: Sender address (optional, for duplicate checking)

        Returns:
            (success, error_message)
        """
        # Check for duplicate
        if tx_hash in self._entries:
            return False, "Transaction already in mempool"

        # Check fee minimum based on tier
        min_fee = self._get_min_fee(privacy_tier, len(tx_data))
        if fee < min_fee:
            return False, f"Fee too low: {fee} < {min_fee}"

        # Check size limit
        if len(self._entries) >= self.max_size:
            # Evict lowest priority transaction
            if not self._evict_lowest():
                return False, "Mempool full"

        # Create entry
        entry = MempoolEntry(
            tx_hash=tx_hash,
            tx_data=tx_data,
            privacy_tier=privacy_tier,
            fee=fee,
            size=len(tx_data),
        )

        # Add to storage
        self._entries[tx_hash] = entry
        heappush(self._priority_queue, entry)

        if sender:
            if sender not in self._by_sender:
                self._by_sender[sender] = set()
            self._by_sender[sender].add(tx_hash)

        logger.debug(
            f"Added tx {tx_hash.hex()[:16]} tier={privacy_tier.name} fee={fee}"
        )

        return True, ""

    def remove(self, tx_hash: Hash) -> bool:
        """
        Remove transaction from mempool.

        Args:
            tx_hash: Transaction to remove

        Returns:
            True if removed
        """
        if tx_hash not in self._entries:
            return False

        entry = self._entries.pop(tx_hash)

        # Remove from sender index
        for sender, tx_set in self._by_sender.items():
            tx_set.discard(tx_hash)

        logger.debug(f"Removed tx {tx_hash.hex()[:16]}")
        return True

    def get(self, tx_hash: Hash) -> Optional[MempoolEntry]:
        """Get transaction by hash."""
        return self._entries.get(tx_hash)

    def contains(self, tx_hash: Hash) -> bool:
        """Check if transaction is in mempool."""
        return tx_hash in self._entries

    def get_transactions(self, count: int = 100) -> List[MempoolEntry]:
        """
        Get highest priority transactions.

        Args:
            count: Maximum number of transactions

        Returns:
            List of transactions sorted by priority
        """
        # Clean expired first
        self._clean_expired()

        # Rebuild priority queue (lazy cleanup of removed entries)
        self._priority_queue = [
            e for e in self._priority_queue
            if e.tx_hash in self._entries
        ]
        self._priority_queue.sort()

        return self._priority_queue[:count]

    def get_by_tier(self, tier: PrivacyTier) -> List[MempoolEntry]:
        """Get all transactions for a specific privacy tier."""
        return [
            e for e in self._entries.values()
            if e.privacy_tier == tier
        ]

    def get_sender_transactions(self, sender: Hash) -> List[MempoolEntry]:
        """Get all transactions from sender."""
        if sender not in self._by_sender:
            return []

        return [
            self._entries[tx_hash]
            for tx_hash in self._by_sender[sender]
            if tx_hash in self._entries
        ]

    def clear(self):
        """Clear all transactions."""
        self._entries.clear()
        self._priority_queue.clear()
        self._by_sender.clear()

    def _get_min_fee(self, tier: PrivacyTier, size: int) -> int:
        """Calculate minimum fee for transaction."""
        multiplier = {
            PrivacyTier.T0_TRANSPARENT: PRIVACY_T0_FEE_MULTIPLIER,
            PrivacyTier.T1_STEALTH: PRIVACY_T1_FEE_MULTIPLIER,
            PrivacyTier.T2_CONFIDENTIAL: PRIVACY_T2_FEE_MULTIPLIER,
            PrivacyTier.T3_RING: PRIVACY_T3_FEE_MULTIPLIER,
        }.get(tier, 1.0)

        return int(MIN_TRANSACTION_FEE * multiplier)

    def _evict_lowest(self) -> bool:
        """Evict lowest priority transaction."""
        if not self._priority_queue:
            return False

        # Find lowest priority entry
        while self._priority_queue:
            entry = heappop(self._priority_queue)
            if entry.tx_hash in self._entries:
                self.remove(entry.tx_hash)
                return True

        return False

    def _clean_expired(self):
        """Remove expired transactions."""
        now = time.time()
        expired = [
            tx_hash
            for tx_hash, entry in self._entries.items()
            if now - entry.added_time > self.max_age_sec
        ]

        for tx_hash in expired:
            self.remove(tx_hash)

        if expired:
            logger.debug(f"Cleaned {len(expired)} expired transactions")

    def get_stats(self) -> Dict:
        """Get mempool statistics."""
        tier_counts = {tier: 0 for tier in PrivacyTier}
        tier_fees = {tier: 0 for tier in PrivacyTier}

        for entry in self._entries.values():
            tier_counts[entry.privacy_tier] += 1
            tier_fees[entry.privacy_tier] += entry.fee

        return {
            "size": len(self._entries),
            "bytes": self.total_bytes,
            "by_tier": {
                tier.name: {
                    "count": tier_counts[tier],
                    "total_fees": tier_fees[tier],
                }
                for tier in PrivacyTier
            },
        }
