"""
Ɉ Montana State Machine v3.1

State transitions per MONTANA_TECHNICAL_SPECIFICATION.md §22.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable, Any
from enum import IntEnum, auto

from montana.constants import (
    MAX_HEARTBEATS_PER_BLOCK,
    MAX_TRANSACTIONS_PER_BLOCK,
    MIN_TRANSACTION_FEE,
)
from montana.core.types import Hash
from montana.core.block import Block
from montana.core.heartbeat import Heartbeat, FullHeartbeat, LightHeartbeat
from montana.state.storage import Database, BlockStore, StateStore
from montana.state.accounts import AccountManager, AccountState

logger = logging.getLogger(__name__)


class TransitionType(IntEnum):
    """Type of state transition."""
    BLOCK = 1           # Block application
    HEARTBEAT = 2       # Heartbeat processing
    TRANSACTION = 3     # Transaction execution
    REWARD = 4          # Block reward
    PENALTY = 5         # Slashing/penalty


@dataclass
class StateTransition:
    """
    Record of a state transition.

    Used for:
    - Audit trail
    - Rollback support
    - State verification
    """
    transition_type: TransitionType
    block_hash: Optional[Hash] = None
    affected_accounts: List[Hash] = None
    changes: Dict[str, Any] = None
    success: bool = True
    error: Optional[str] = None

    def __post_init__(self):
        if self.affected_accounts is None:
            self.affected_accounts = []
        if self.changes is None:
            self.changes = {}


class StateMachine:
    """
    State machine for block and transaction processing.

    Handles:
    - Block application
    - Heartbeat processing
    - Transaction execution
    - Reward distribution
    - State root computation
    """

    def __init__(
        self,
        db: Database,
        block_store: BlockStore,
        state_store: StateStore,
        account_manager: AccountManager,
    ):
        self.db = db
        self.block_store = block_store
        self.state_store = state_store
        self.accounts = account_manager

        # Transition log
        self._transitions: List[StateTransition] = []

        # Hooks
        self._on_block_applied: List[Callable[[Block], Any]] = []
        self._on_heartbeat: List[Callable[[Heartbeat], Any]] = []

    async def apply_block(self, block: Block) -> StateTransition:
        """
        Apply block to state.

        Processes:
        1. Validate block structure
        2. Process heartbeats
        3. Execute transactions
        4. Distribute rewards
        5. Update state root

        Args:
            block: Block to apply

        Returns:
            StateTransition with result
        """
        transition = StateTransition(
            transition_type=TransitionType.BLOCK,
            block_hash=block.hash(),
        )

        try:
            # Validate structure
            valid, error = block.validate_structure()
            if not valid:
                transition.success = False
                transition.error = error
                return transition

            # Process heartbeats
            heartbeat_results = await self._process_heartbeats(block)
            transition.changes["heartbeats"] = len(block.heartbeats)

            # Execute transactions
            tx_results = await self._execute_transactions(block)
            transition.changes["transactions"] = len(block.transactions)
            transition.changes["tx_success"] = sum(1 for r in tx_results if r[0])
            transition.changes["tx_failed"] = sum(1 for r in tx_results if not r[0])

            # Distribute block reward
            await self._distribute_reward(block)
            transition.changes["producer"] = block.header.producer_id.hex()[:16]

            # Store block
            await self.block_store.add_block(block)

            # Update best block
            await self.state_store.set_best_block_hash(block.hash())

            # Collect affected accounts
            transition.affected_accounts = list(set(
                [block.header.producer_id] +
                [h[0] for h in heartbeat_results] +
                [t[1] for t in tx_results if t[1]]
            ))

            transition.success = True

            # Trigger hooks
            for hook in self._on_block_applied:
                try:
                    hook(block)
                except Exception as e:
                    logger.warning(f"Block hook error: {e}")

            logger.info(
                f"Applied block {block.hash().hex()[:16]} "
                f"height={block.height} "
                f"hb={len(block.heartbeats)} tx={len(block.transactions)}"
            )

        except Exception as e:
            transition.success = False
            transition.error = str(e)
            logger.error(f"Failed to apply block: {e}")

        self._transitions.append(transition)
        return transition

    async def _process_heartbeats(
        self,
        block: Block,
    ) -> List[Tuple[Hash, bool]]:
        """
        Process heartbeats in block.

        Returns:
            List of (node_id, success) tuples
        """
        results = []

        for hb_data in block.heartbeats:
            try:
                # Deserialize based on first byte (node_type)
                if len(hb_data) > 1:
                    # Try full heartbeat first
                    try:
                        hb, _ = FullHeartbeat.deserialize(hb_data)
                    except Exception:
                        hb, _ = LightHeartbeat.deserialize(hb_data)

                    # Record heartbeat
                    await self.accounts.record_heartbeat(
                        hb.node_id,
                        hb.timestamp_ms,
                        precision_factor=1.0,  # Would come from VDF verification
                    )

                    results.append((hb.node_id, True))

                    # Trigger hooks
                    for hook in self._on_heartbeat:
                        try:
                            hook(hb)
                        except Exception as e:
                            logger.warning(f"Heartbeat hook error: {e}")

            except Exception as e:
                logger.warning(f"Failed to process heartbeat: {e}")
                results.append((Hash.zero(), False))

        return results

    async def _execute_transactions(
        self,
        block: Block,
    ) -> List[Tuple[bool, Optional[Hash], str]]:
        """
        Execute transactions in block.

        Returns:
            List of (success, sender_hash, error) tuples
        """
        results = []

        for tx_data in block.transactions:
            try:
                # Transaction deserialization would happen here
                # For now, placeholder
                results.append((True, None, ""))

            except Exception as e:
                results.append((False, None, str(e)))

        return results

    async def _distribute_reward(self, block: Block):
        """
        Distribute block reward to producer.

        Reward calculation per §12.
        """
        # Base reward (would be calculated based on emission schedule)
        base_reward = 1_000_000  # 1 MONT in microMONT

        # Get producer account
        producer = await self.accounts.get_account(block.header.producer_id)
        producer.credit(base_reward)
        await self.accounts.save_account(producer)

        logger.debug(
            f"Distributed reward {base_reward} to {block.header.producer_id.hex()[:16]}"
        )

    async def compute_state_root(self) -> Hash:
        """
        Compute state root from current state.

        Uses Merkle tree of account states.
        """
        from montana.crypto.hash import sha3_256, HashBuilder

        # Get all accounts sorted by address
        rows = await self.db.fetchall(
            """
            SELECT address, balance, nonce, heartbeat_count
            FROM accounts
            ORDER BY address
            """
        )

        if not rows:
            return Hash.zero()

        # Build Merkle tree
        hashes = []
        for row in rows:
            # Hash account state
            data = (
                row["address"] +
                row["balance"].to_bytes(8, 'big') +
                row["nonce"].to_bytes(8, 'big') +
                row["heartbeat_count"].to_bytes(8, 'big')
            )
            hashes.append(sha3_256(data))

        # Build tree
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])

            next_level = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i].data + hashes[i + 1].data
                next_level.append(sha3_256(combined))
            hashes = next_level

        return hashes[0]

    async def verify_state_root(self, block: Block) -> bool:
        """
        Verify block's state root matches computed root.

        Args:
            block: Block to verify

        Returns:
            True if state root matches
        """
        computed = await self.compute_state_root()
        return computed == block.header.state_root

    async def rollback_block(self, block_hash: Hash) -> bool:
        """
        Rollback block application.

        Used for chain reorganization.
        """
        # Find transition for this block
        for i, t in enumerate(self._transitions):
            if t.block_hash == block_hash:
                # Rollback would require reversing all changes
                # This is a placeholder - full implementation would
                # store undo data during apply
                logger.warning(f"Rollback not fully implemented for {block_hash.hex()[:16]}")
                return False

        return False

    def on_block_applied(self, handler: Callable[[Block], Any]):
        """Register handler for block application."""
        self._on_block_applied.append(handler)

    def on_heartbeat(self, handler: Callable[[Heartbeat], Any]):
        """Register handler for heartbeat processing."""
        self._on_heartbeat.append(handler)

    def get_recent_transitions(self, count: int = 100) -> List[StateTransition]:
        """Get recent state transitions."""
        return self._transitions[-count:]
