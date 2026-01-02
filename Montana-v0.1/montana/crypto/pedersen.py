"""
Ɉ Montana Pedersen Commitments v3.1

T2 Privacy: Hidden amounts via Pedersen commitments per §14.3.

Pedersen commitments allow hiding transaction amounts while
still enabling verification that inputs = outputs.

C = v*G + r*H

Where:
- v is the value (amount)
- r is the blinding factor (random)
- G, H are generator points
"""

from __future__ import annotations
import secrets
import hashlib
from dataclasses import dataclass
from typing import Tuple, List

from montana.constants import PEDERSEN_H_GENERATOR_SEED
from montana.crypto.hash import sha3_256, shake256


# Simulated curve order (in production, use actual curve parameters)
CURVE_ORDER = 2**252 + 27742317777372353535851937790883648493


@dataclass(frozen=True)
class PedersenCommitment:
    """
    Pedersen commitment to a value.

    Hides the value while allowing verification
    that sum of inputs equals sum of outputs.
    """
    commitment: bytes      # 32 bytes - the commitment C = v*G + r*H

    def serialize(self) -> bytes:
        return self.commitment

    @classmethod
    def deserialize(cls, data: bytes) -> "PedersenCommitment":
        return cls(commitment=data[:32])

    def __add__(self, other: "PedersenCommitment") -> "PedersenCommitment":
        """Add two commitments (homomorphic addition)."""
        # Simplified: XOR-based addition for demonstration
        # In production, use proper elliptic curve point addition
        result = bytes(a ^ b for a, b in zip(self.commitment, other.commitment))
        return PedersenCommitment(commitment=result)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PedersenCommitment):
            return self.commitment == other.commitment
        return False


@dataclass
class CommitmentOpening:
    """
    Opening for a Pedersen commitment.

    Contains the secret values needed to verify/spend.
    """
    value: int             # The committed value
    blinding: bytes        # 32 bytes - the blinding factor r


def _point_mul(scalar: bytes, generator_seed: bytes) -> bytes:
    """
    Simulated scalar multiplication on curve.

    In production, use proper elliptic curve operations.
    """
    return sha3_256(scalar + generator_seed).data


def _point_add(p1: bytes, p2: bytes) -> bytes:
    """
    Simulated point addition on curve.

    In production, use proper elliptic curve operations.
    """
    return sha3_256(p1 + p2 + b"ADD").data


def get_generator_h() -> bytes:
    """
    Get the H generator point.

    H is derived deterministically from a seed to ensure
    nobody knows the discrete log relationship between G and H.
    """
    return sha3_256(PEDERSEN_H_GENERATOR_SEED).data


def commit(value: int, blinding: bytes = None) -> Tuple[PedersenCommitment, CommitmentOpening]:
    """
    Create Pedersen commitment to a value.

    C = v*G + r*H

    Args:
        value: The value to commit to
        blinding: Optional blinding factor (generated if not provided)

    Returns:
        (commitment, opening)
    """
    if blinding is None:
        blinding = secrets.token_bytes(32)

    # Convert value to bytes
    value_bytes = value.to_bytes(32, 'big')

    # Compute v*G (using value as scalar, G is implicit base point)
    v_g = _point_mul(value_bytes, b"MONTANA_GENERATOR_G")

    # Compute r*H
    h = get_generator_h()
    r_h = _point_mul(blinding, h)

    # C = v*G + r*H
    commitment_bytes = _point_add(v_g, r_h)

    commitment = PedersenCommitment(commitment=commitment_bytes)
    opening = CommitmentOpening(value=value, blinding=blinding)

    return commitment, opening


def verify_commitment(
    commitment: PedersenCommitment,
    opening: CommitmentOpening,
) -> bool:
    """
    Verify that a commitment matches its opening.

    Args:
        commitment: The commitment to verify
        opening: The claimed opening (value, blinding)

    Returns:
        True if commitment is valid
    """
    expected, _ = commit(opening.value, opening.blinding)
    return commitment == expected


def verify_sum(
    input_commitments: List[PedersenCommitment],
    output_commitments: List[PedersenCommitment],
    fee_commitment: PedersenCommitment = None,
) -> bool:
    """
    Verify that sum of inputs equals sum of outputs (+ fee).

    Due to homomorphic property:
    sum(input_C) = sum(output_C) + fee_C

    If the blinding factors also sum correctly.

    Args:
        input_commitments: Commitments from inputs
        output_commitments: Commitments from outputs
        fee_commitment: Optional fee commitment

    Returns:
        True if sums balance
    """
    if not input_commitments:
        return False

    # Sum inputs
    input_sum = input_commitments[0]
    for c in input_commitments[1:]:
        input_sum = input_sum + c

    # Sum outputs
    if output_commitments:
        output_sum = output_commitments[0]
        for c in output_commitments[1:]:
            output_sum = output_sum + c
    else:
        output_sum = PedersenCommitment(commitment=bytes(32))

    # Add fee if present
    if fee_commitment:
        output_sum = output_sum + fee_commitment

    return input_sum == output_sum


def create_range_proof(
    commitment: PedersenCommitment,
    opening: CommitmentOpening,
    bits: int = 64,
) -> bytes:
    """
    Create range proof that committed value is in [0, 2^bits).

    This is a simplified placeholder. In production, use Bulletproofs.

    Args:
        commitment: The commitment
        opening: The opening with value and blinding
        bits: Number of bits for range (value must be < 2^bits)

    Returns:
        Range proof bytes
    """
    if opening.value < 0 or opening.value >= 2**bits:
        raise ValueError(f"Value {opening.value} out of range [0, 2^{bits})")

    # Simplified range proof: hash of commitment and value
    # In production, use Bulletproofs for O(log n) proof size
    proof_data = sha3_256(
        commitment.commitment +
        opening.value.to_bytes(8, 'big') +
        opening.blinding +
        b"RANGE_PROOF"
    ).data

    return proof_data


def verify_range_proof(
    commitment: PedersenCommitment,
    proof: bytes,
    bits: int = 64,
) -> bool:
    """
    Verify range proof.

    In production, this would verify a Bulletproof.
    This simplified version always returns True for valid-length proofs.
    """
    return len(proof) == 32
