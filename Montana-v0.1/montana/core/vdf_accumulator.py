"""
Ɉ Montana VDF Accumulator v3.1

Layer 2: Accumulated Finality per MONTANA_TECHNICAL_SPECIFICATION.md §6.

Implements three finality levels through VDF checkpoint accumulation:
- Soft:   1 checkpoint   (~2.5 seconds)  - Fast confirmation
- Medium: 100 checkpoints (~4 minutes)   - Standard confirmation
- Hard:   1000 checkpoints (~40 minutes) - Maximum security
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum

from montana.constants import (
    VDF_CHECKPOINT_TIME_SEC,
    FINALITY_SOFT_CHECKPOINTS,
    FINALITY_MEDIUM_CHECKPOINTS,
    FINALITY_HARD_CHECKPOINTS,
    VDF_BASE_ITERATIONS,
)
from montana.core.types import Hash
from montana.core.vdf import VDFOutput, VDFProof, SHAKE256VDF, get_vdf

logger = logging.getLogger(__name__)


class FinalityLevel(IntEnum):
    """
    Finality levels per §6.2.

    Each level represents accumulated VDF checkpoints providing
    increasing confidence in temporal ordering.
    """
    NONE = 0      # No finality (pending)
    SOFT = 1      # 1 checkpoint (~2.5s)
    MEDIUM = 2    # 100 checkpoints (~4min)
    HARD = 3      # 1000 checkpoints (~40min)


@dataclass
class FinalityThresholds:
    """Checkpoint thresholds for each finality level."""
    soft: int = FINALITY_SOFT_CHECKPOINTS      # 1
    medium: int = FINALITY_MEDIUM_CHECKPOINTS  # 100
    hard: int = FINALITY_HARD_CHECKPOINTS      # 1000


@dataclass
class AccumulatedState:
    """
    Accumulated VDF state for a block or transaction.

    Tracks the accumulation of VDF checkpoints to determine
    current finality level.
    """
    block_hash: Hash                           # Block this state belongs to
    initial_vdf_output: Hash                   # VDF output at block creation
    accumulated_checkpoints: int = 0           # Total accumulated checkpoints
    last_checkpoint_time: float = 0.0          # Timestamp of last checkpoint
    proofs: List[VDFProof] = field(default_factory=list)  # Accumulated proofs

    @property
    def finality_level(self) -> FinalityLevel:
        """Determine current finality level from accumulated checkpoints."""
        if self.accumulated_checkpoints >= FINALITY_HARD_CHECKPOINTS:
            return FinalityLevel.HARD
        elif self.accumulated_checkpoints >= FINALITY_MEDIUM_CHECKPOINTS:
            return FinalityLevel.MEDIUM
        elif self.accumulated_checkpoints >= FINALITY_SOFT_CHECKPOINTS:
            return FinalityLevel.SOFT
        return FinalityLevel.NONE

    @property
    def estimated_time_to_hard(self) -> float:
        """Estimate seconds until hard finality."""
        remaining = FINALITY_HARD_CHECKPOINTS - self.accumulated_checkpoints
        if remaining <= 0:
            return 0.0
        return remaining * VDF_CHECKPOINT_TIME_SEC

    def add_checkpoint(self, proof: VDFProof) -> FinalityLevel:
        """
        Add a VDF checkpoint and return new finality level.

        Args:
            proof: VDF proof for this checkpoint

        Returns:
            Current finality level after adding checkpoint
        """
        self.accumulated_checkpoints += 1
        self.last_checkpoint_time = time.time()
        self.proofs.append(proof)
        return self.finality_level


class VDFAccumulator:
    """
    VDF checkpoint accumulator for finality per §6.

    Manages the accumulation of VDF checkpoints across blocks,
    computing finality levels and chain selection.
    """

    def __init__(
        self,
        thresholds: Optional[FinalityThresholds] = None,
        vdf: Optional[SHAKE256VDF] = None,
    ):
        """
        Initialize accumulator.

        Args:
            thresholds: Custom finality thresholds
            vdf: VDF instance to use (defaults to global)
        """
        self.thresholds = thresholds or FinalityThresholds()
        self.vdf = vdf or get_vdf()

        # State tracking per block
        self._states: Dict[Hash, AccumulatedState] = {}

        # Current chain tip
        self._chain_tip: Optional[Hash] = None

    def register_block(self, block_hash: Hash, vdf_output: Hash) -> AccumulatedState:
        """
        Register a new block for finality tracking.

        Args:
            block_hash: Hash of the block
            vdf_output: VDF output included in block

        Returns:
            New AccumulatedState for the block
        """
        if block_hash in self._states:
            return self._states[block_hash]

        state = AccumulatedState(
            block_hash=block_hash,
            initial_vdf_output=vdf_output,
            last_checkpoint_time=time.time(),
        )
        self._states[block_hash] = state

        logger.debug(f"Registered block {block_hash.hex()[:16]} for finality tracking")
        return state

    def add_checkpoint(self, block_hash: Hash, proof: VDFProof) -> Optional[FinalityLevel]:
        """
        Add a VDF checkpoint to a block's finality.

        Args:
            block_hash: Block to add checkpoint to
            proof: VDF proof for this checkpoint

        Returns:
            New finality level, or None if block not found
        """
        state = self._states.get(block_hash)
        if state is None:
            logger.warning(f"Block {block_hash.hex()[:16]} not registered")
            return None

        # Verify proof chains from previous state
        if state.proofs:
            last_proof = state.proofs[-1]
            if proof.input_hash != last_proof.output_hash:
                logger.warning("VDF proof doesn't chain from previous output")
                return None
        else:
            if proof.input_hash != state.initial_vdf_output:
                logger.warning("VDF proof doesn't chain from block VDF output")
                return None

        # Verify the proof itself
        if not self.vdf.verify_proof(proof):
            logger.warning("VDF proof verification failed")
            return None

        # Add checkpoint
        old_level = state.finality_level
        new_level = state.add_checkpoint(proof)

        if new_level != old_level:
            logger.info(
                f"Block {block_hash.hex()[:16]} reached {new_level.name} finality "
                f"({state.accumulated_checkpoints} checkpoints)"
            )

        return new_level

    def get_finality(self, block_hash: Hash) -> FinalityLevel:
        """Get current finality level for a block."""
        state = self._states.get(block_hash)
        if state is None:
            return FinalityLevel.NONE
        return state.finality_level

    def get_state(self, block_hash: Hash) -> Optional[AccumulatedState]:
        """Get accumulated state for a block."""
        return self._states.get(block_hash)

    def compare_finality(self, hash_a: Hash, hash_b: Hash) -> int:
        """
        Compare finality between two blocks.

        Returns:
            1 if A has more finality, -1 if B has more, 0 if equal
        """
        level_a = self.get_finality(hash_a)
        level_b = self.get_finality(hash_b)

        if level_a > level_b:
            return 1
        elif level_b > level_a:
            return -1

        # Same level - compare checkpoint counts
        state_a = self._states.get(hash_a)
        state_b = self._states.get(hash_b)

        if state_a and state_b:
            if state_a.accumulated_checkpoints > state_b.accumulated_checkpoints:
                return 1
            elif state_b.accumulated_checkpoints > state_a.accumulated_checkpoints:
                return -1

        return 0

    def select_chain_tip(self, candidates: List[Hash]) -> Optional[Hash]:
        """
        Select chain tip from candidates based on accumulated finality.

        This implements the fork choice rule per §6.3:
        "The chain with the most accumulated VDF work is canonical."

        Args:
            candidates: List of candidate block hashes

        Returns:
            Hash of the block with most accumulated finality
        """
        if not candidates:
            return None

        best = candidates[0]
        for candidate in candidates[1:]:
            if self.compare_finality(candidate, best) > 0:
                best = candidate

        self._chain_tip = best
        return best

    def prune_old_states(self, keep_hashes: set[Hash]) -> int:
        """
        Remove states for blocks not in keep_hashes.

        Args:
            keep_hashes: Set of block hashes to keep

        Returns:
            Number of states pruned
        """
        to_remove = [h for h in self._states if h not in keep_hashes]
        for h in to_remove:
            del self._states[h]
        return len(to_remove)

    @property
    def chain_tip(self) -> Optional[Hash]:
        """Current chain tip based on finality."""
        return self._chain_tip

    def get_finality_stats(self) -> Dict[str, int]:
        """Get statistics about tracked blocks by finality level."""
        stats = {level.name: 0 for level in FinalityLevel}
        for state in self._states.values():
            stats[state.finality_level.name] += 1
        return stats


# Global accumulator instance
_accumulator: Optional[VDFAccumulator] = None


def get_accumulator() -> VDFAccumulator:
    """Get or create global VDF accumulator."""
    global _accumulator
    if _accumulator is None:
        _accumulator = VDFAccumulator()
    return _accumulator


def get_finality_time(level: FinalityLevel) -> float:
    """
    Get expected time to reach finality level.

    Args:
        level: Target finality level

    Returns:
        Expected time in seconds
    """
    checkpoints = {
        FinalityLevel.NONE: 0,
        FinalityLevel.SOFT: FINALITY_SOFT_CHECKPOINTS,
        FinalityLevel.MEDIUM: FINALITY_MEDIUM_CHECKPOINTS,
        FinalityLevel.HARD: FINALITY_HARD_CHECKPOINTS,
    }
    return checkpoints.get(level, 0) * VDF_CHECKPOINT_TIME_SEC
