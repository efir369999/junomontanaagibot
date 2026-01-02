"""
Ɉ Montana Account State v3.1

Account management per MONTANA_TECHNICAL_SPECIFICATION.md §21.
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from montana.constants import (
    INITIAL_BALANCE,
    MIN_TRANSACTION_FEE,
    SCORE_SQRT_COEFFICIENT,
)
from montana.core.types import Hash, PrivacyTier
from montana.state.storage import Database

logger = logging.getLogger(__name__)


@dataclass
class AccountState:
    """
    Account state per §21.1.

    Tracks:
    - Balance (in microMONT, 1 MONT = 1e6 microMONT)
    - Nonce (for replay protection)
    - Privacy tier preference
    - Heartbeat statistics
    - Participation score
    """
    address: Hash                           # Account address (32 bytes)
    balance: int = 0                        # Balance in microMONT
    nonce: int = 0                          # Transaction nonce
    privacy_tier: PrivacyTier = PrivacyTier.T0
    heartbeat_count: int = 0                # Total heartbeats
    score: float = 0.0                      # Participation score
    last_heartbeat_ms: int = 0              # Last heartbeat timestamp

    @property
    def balance_mont(self) -> float:
        """Balance in MONT."""
        return self.balance / 1_000_000

    def apply_heartbeat(self, timestamp_ms: int, precision_factor: float = 1.0):
        """
        Apply heartbeat to account.

        Updates heartbeat count, score, and timestamp.
        Score = sqrt(heartbeats) * precision per §8.2.
        """
        self.heartbeat_count += 1
        self.score = math.sqrt(self.heartbeat_count) * precision_factor * SCORE_SQRT_COEFFICIENT
        self.last_heartbeat_ms = timestamp_ms

    def can_send(self, amount: int, fee: int = MIN_TRANSACTION_FEE) -> Tuple[bool, str]:
        """
        Check if account can send amount + fee.

        Returns:
            (can_send, error_message)
        """
        total = amount + fee
        if total > self.balance:
            return False, f"Insufficient balance: {self.balance} < {total}"
        if amount < 0:
            return False, "Negative amount"
        if fee < MIN_TRANSACTION_FEE:
            return False, f"Fee too low: {fee} < {MIN_TRANSACTION_FEE}"
        return True, ""

    def debit(self, amount: int, fee: int = 0) -> bool:
        """
        Debit amount + fee from account.

        Returns:
            True if successful
        """
        total = amount + fee
        if total > self.balance:
            return False
        self.balance -= total
        self.nonce += 1
        return True

    def credit(self, amount: int):
        """Credit amount to account."""
        self.balance += amount


class AccountManager:
    """
    Manages account state.

    Provides:
    - Account lookup and creation
    - Balance operations
    - Heartbeat tracking
    - Score calculation
    """

    def __init__(self, db: Database):
        self.db = db
        self._cache: Dict[Hash, AccountState] = {}

    async def get_account(self, address: Hash) -> AccountState:
        """
        Get account by address.

        Creates new account if not exists.
        """
        # Check cache
        if address in self._cache:
            return self._cache[address]

        # Query database
        row = await self.db.fetchone(
            """
            SELECT address, balance, nonce, privacy_tier,
                   heartbeat_count, score, last_heartbeat_ms
            FROM accounts WHERE address = ?
            """,
            (address.data,)
        )

        if row:
            account = AccountState(
                address=Hash(row["address"]),
                balance=row["balance"],
                nonce=row["nonce"],
                privacy_tier=PrivacyTier(row["privacy_tier"]),
                heartbeat_count=row["heartbeat_count"],
                score=row["score"],
                last_heartbeat_ms=row["last_heartbeat_ms"] or 0,
            )
        else:
            # Create new account
            account = AccountState(
                address=address,
                balance=0,
                nonce=0,
            )

        self._cache[address] = account
        return account

    async def save_account(self, account: AccountState):
        """Save account to database."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO accounts
            (address, balance, nonce, privacy_tier,
             heartbeat_count, score, last_heartbeat_ms, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            """,
            (
                account.address.data,
                account.balance,
                account.nonce,
                account.privacy_tier,
                account.heartbeat_count,
                account.score,
                account.last_heartbeat_ms,
            )
        )
        self._cache[account.address] = account

    async def transfer(
        self,
        sender: Hash,
        recipient: Hash,
        amount: int,
        fee: int = MIN_TRANSACTION_FEE,
    ) -> Tuple[bool, str]:
        """
        Transfer amount from sender to recipient.

        Returns:
            (success, error_message)
        """
        sender_account = await self.get_account(sender)
        recipient_account = await self.get_account(recipient)

        # Check balance
        can_send, error = sender_account.can_send(amount, fee)
        if not can_send:
            return False, error

        # Execute transfer
        sender_account.debit(amount, fee)
        recipient_account.credit(amount)

        # Save both accounts
        await self.save_account(sender_account)
        await self.save_account(recipient_account)

        logger.debug(
            f"Transfer: {sender.hex()[:16]} -> {recipient.hex()[:16]}: "
            f"{amount} (fee: {fee})"
        )

        return True, ""

    async def record_heartbeat(
        self,
        node_id: Hash,
        timestamp_ms: int,
        precision_factor: float = 1.0,
    ):
        """Record heartbeat for node."""
        account = await self.get_account(node_id)
        account.apply_heartbeat(timestamp_ms, precision_factor)
        await self.save_account(account)

    async def get_top_by_score(self, limit: int = 100) -> List[AccountState]:
        """Get accounts with highest scores."""
        rows = await self.db.fetchall(
            """
            SELECT address, balance, nonce, privacy_tier,
                   heartbeat_count, score, last_heartbeat_ms
            FROM accounts
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,)
        )

        accounts = []
        for row in rows:
            account = AccountState(
                address=Hash(row["address"]),
                balance=row["balance"],
                nonce=row["nonce"],
                privacy_tier=PrivacyTier(row["privacy_tier"]),
                heartbeat_count=row["heartbeat_count"],
                score=row["score"],
                last_heartbeat_ms=row["last_heartbeat_ms"] or 0,
            )
            accounts.append(account)

        return accounts

    async def get_total_supply(self) -> int:
        """Get total supply (sum of all balances)."""
        row = await self.db.fetchone(
            "SELECT SUM(balance) as total FROM accounts"
        )
        return row["total"] if row and row["total"] else 0

    async def get_account_count(self) -> int:
        """Get total number of accounts."""
        row = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM accounts"
        )
        return row["count"] if row else 0

    def clear_cache(self):
        """Clear account cache."""
        self._cache.clear()
