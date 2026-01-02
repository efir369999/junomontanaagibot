"""
Ɉ Montana Block Eligibility v3.1

Block production eligibility per MONTANA_TECHNICAL_SPECIFICATION.md §10.

Uses VRF-based lottery for fair block producer selection.
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from montana.core.types import Hash, PublicKey, ParticipationTier
from montana.crypto.vrf import vrf_prove, vrf_verify, VRFOutput, is_lottery_winner
from montana.crypto.hash import sha3_256


@dataclass
class EligibilityProof:
    """
    Proof of block production eligibility.

    Contains VRF output proving the node was selected
    for this slot.
    """
    slot: int                     # Block slot/height
    vrf_output: VRFOutput         # VRF proof
    tier: ParticipationTier       # Node's participation tier
    score: int                    # Node's score at time of proof

    def serialize(self) -> bytes:
        from montana.core.serialization import ByteWriter
        w = ByteWriter()
        w.write_u64(self.slot)
        w.write_raw(self.vrf_output.serialize())
        w.write_u8(self.tier)
        w.write_u64(self.score)
        return w.to_bytes()


def compute_lottery_input(
    prev_vdf_output: Hash,
    slot: int,
    node_id: Hash,
) -> bytes:
    """
    Compute VRF input for lottery.

    Input is deterministic based on previous VDF output,
    slot number, and node ID.
    """
    return sha3_256(
        prev_vdf_output.data +
        slot.to_bytes(8, 'big') +
        node_id.data +
        b"MONTANA_LOTTERY"
    ).data


def compute_threshold(
    tier: ParticipationTier,
    score: int,
    total_score: int,
    tier_weight: float,
) -> int:
    """
    Compute lottery threshold based on tier and score.

    Higher score = higher threshold = higher chance of winning.

    Args:
        tier: Participation tier (affects base weight)
        score: Node's score
        total_score: Total network score
        tier_weight: Weight for this tier (0.7, 0.2, or 0.1)

    Returns:
        Threshold value (VRF output must be below this to win)
    """
    if total_score == 0:
        return 0

    # Base probability from tier
    base_prob = tier_weight

    # Score-based probability within tier
    score_ratio = score / total_score

    # Combined probability
    prob = base_prob * score_ratio

    # Convert to threshold (prob * max_value)
    max_value = 2**256 - 1
    threshold = int(prob * max_value)

    return threshold


def check_eligibility(
    secret_key: bytes,
    public_key: bytes,
    node_id: Hash,
    prev_vdf_output: Hash,
    slot: int,
    tier: ParticipationTier,
    score: int,
    total_score: int,
) -> Optional[EligibilityProof]:
    """
    Check if node is eligible to produce block at slot.

    Args:
        secret_key: Node's VRF secret key
        public_key: Node's VRF public key
        node_id: Node identifier
        prev_vdf_output: Previous block's VDF output
        slot: Slot to check
        tier: Node's participation tier
        score: Node's score
        total_score: Total network score

    Returns:
        EligibilityProof if eligible, None otherwise
    """
    from montana.constants import TIER_WEIGHTS

    # Compute lottery input
    lottery_input = compute_lottery_input(prev_vdf_output, slot, node_id)

    # Generate VRF output
    vrf_output = vrf_prove(secret_key, lottery_input)

    # Get tier weight
    tier_weight = TIER_WEIGHTS.get(tier, 0.0)

    # Compute threshold
    threshold = compute_threshold(tier, score, total_score, tier_weight)

    # Check if winner
    if is_lottery_winner(vrf_output.beta, threshold):
        return EligibilityProof(
            slot=slot,
            vrf_output=vrf_output,
            tier=tier,
            score=score,
        )

    return None


def verify_eligibility(
    proof: EligibilityProof,
    public_key: bytes,
    node_id: Hash,
    prev_vdf_output: Hash,
    total_score: int,
) -> bool:
    """
    Verify eligibility proof.

    Args:
        proof: Eligibility proof to verify
        public_key: Producer's VRF public key
        node_id: Producer's node ID
        prev_vdf_output: Previous block's VDF output
        total_score: Total network score at that slot

    Returns:
        True if proof is valid
    """
    from montana.constants import TIER_WEIGHTS

    # Compute expected lottery input
    lottery_input = compute_lottery_input(prev_vdf_output, proof.slot, node_id)

    # Verify VRF
    if not vrf_verify(public_key, lottery_input, proof.vrf_output):
        return False

    # Get tier weight
    tier_weight = TIER_WEIGHTS.get(proof.tier, 0.0)

    # Compute threshold
    threshold = compute_threshold(
        proof.tier, proof.score, total_score, tier_weight
    )

    # Verify winner
    return is_lottery_winner(proof.vrf_output.beta, threshold)


class BlockEligibility:
    """
    Wrapper class for block eligibility checking.

    Provides object-oriented interface to eligibility functions.
    """

    def __init__(self, total_score: int = 1000):
        self.total_score = total_score

    def check_eligibility(
        self,
        vrf_output: Hash,
        node_id: Hash,
        score: float,
        tier: ParticipationTier = ParticipationTier.TIER_1,
    ) -> bool:
        """
        Simple eligibility check without VRF computation.

        For use when VRF output is already available.
        """
        from montana.constants import TIER_WEIGHTS

        tier_weight = TIER_WEIGHTS.get(tier, 0.0)
        threshold = compute_threshold(
            tier,
            int(score * 1000),
            self.total_score,
            tier_weight
        )

        return is_lottery_winner(vrf_output.data, threshold)

    def update_total_score(self, new_total: int):
        """Update total network score."""
        self.total_score = new_total
