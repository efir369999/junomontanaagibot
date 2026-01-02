"""
Montana STARK Integration

This module provides Python interface to the Rust STARK library
for VDF proof generation and verification.

Usage:
    from montana.crypto.stark import generate_vdf_proof, verify_vdf_proof

    # Generate proof (after VDF computation)
    proof = generate_vdf_proof(input_hash, output_hash, checkpoints)

    # Verify proof (O(log T) instead of O(T))
    is_valid = verify_vdf_proof(input_hash, output_hash, proof)
"""

from typing import List, Optional
from dataclasses import dataclass

# Try to import Rust bindings, fall back to stub if not built
try:
    from montana_stark import (
        py_generate_proof,
        py_verify_proof,
        py_get_proof_size,
        py_stark_available,
        PyVdfProof,
    )
    STARK_AVAILABLE = py_stark_available()
except ImportError:
    STARK_AVAILABLE = False
    PyVdfProof = None


# Constants (must match Rust and spec)
VDF_ITERATIONS = 16_777_216  # 2^24
VDF_CHECKPOINT_INTERVAL = 1000
STARK_SECURITY_BITS = 128


@dataclass
class VdfProofResult:
    """Result of VDF proof generation."""
    proof_bytes: bytes
    iterations: int
    checkpoint_interval: int
    proof_size: int


def is_stark_available() -> bool:
    """Check if STARK library is available."""
    return STARK_AVAILABLE


def generate_vdf_proof(
    input_hash: bytes,
    output_hash: bytes,
    checkpoints: List[bytes],
    iterations: int = VDF_ITERATIONS,
) -> Optional[VdfProofResult]:
    """
    Generate STARK proof for VDF computation.

    Args:
        input_hash: 32-byte input to VDF
        output_hash: 32-byte output of VDF
        checkpoints: List of 32-byte intermediate hashes
        iterations: Total number of hash iterations

    Returns:
        VdfProofResult containing the proof, or None if STARK unavailable

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If proof generation fails
    """
    if not STARK_AVAILABLE:
        return None

    # Validate inputs
    if len(input_hash) != 32:
        raise ValueError("input_hash must be 32 bytes")
    if len(output_hash) != 32:
        raise ValueError("output_hash must be 32 bytes")
    for i, cp in enumerate(checkpoints):
        if len(cp) != 32:
            raise ValueError(f"checkpoint {i} must be 32 bytes")

    # Generate proof via Rust
    proof = py_generate_proof(
        input_hash,
        output_hash,
        checkpoints,
        iterations,
    )

    # Serialize and return
    proof_bytes = proof.to_bytes()
    return VdfProofResult(
        proof_bytes=proof_bytes,
        iterations=iterations,
        checkpoint_interval=VDF_CHECKPOINT_INTERVAL,
        proof_size=len(proof_bytes),
    )


def verify_vdf_proof(
    input_hash: bytes,
    output_hash: bytes,
    proof: bytes,
    iterations: int = VDF_ITERATIONS,
) -> bool:
    """
    Verify STARK proof for VDF computation.

    This is O(log T) instead of O(T) for full recomputation.

    Args:
        input_hash: 32-byte input to VDF
        output_hash: 32-byte output of VDF
        proof: Serialized STARK proof bytes
        iterations: Total number of hash iterations

    Returns:
        True if proof is valid, False otherwise

    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If STARK library unavailable
    """
    if not STARK_AVAILABLE:
        raise RuntimeError(
            "STARK library not available. "
            "Build montana-stark with: cd montana-stark && maturin develop --release"
        )

    # Validate inputs
    if len(input_hash) != 32:
        raise ValueError("input_hash must be 32 bytes")
    if len(output_hash) != 32:
        raise ValueError("output_hash must be 32 bytes")

    # Deserialize proof
    py_proof = PyVdfProof.from_bytes(proof)

    # Verify via Rust
    return py_verify_proof(input_hash, output_hash, py_proof, iterations)


def get_expected_proof_size(
    iterations: int = VDF_ITERATIONS,
    checkpoint_interval: int = VDF_CHECKPOINT_INTERVAL,
) -> int:
    """
    Get expected proof size for given parameters.

    Args:
        iterations: Total VDF iterations
        checkpoint_interval: Checkpoint save frequency

    Returns:
        Expected proof size in bytes
    """
    if STARK_AVAILABLE:
        return py_get_proof_size(iterations, checkpoint_interval)

    # Fallback estimate
    import math
    num_checkpoints = iterations // checkpoint_interval
    fri_layers = int(math.ceil(math.log2(num_checkpoints)))
    return 256 + fri_layers * 64 + 32 * 30  # Rough estimate


def verify_vdf_by_recomputation(
    input_hash: bytes,
    output_hash: bytes,
    iterations: int = VDF_ITERATIONS,
) -> bool:
    """
    Verify VDF by full recomputation (fallback when STARK unavailable).

    WARNING: This takes O(T) time (~2.5 seconds for default iterations).

    Args:
        input_hash: 32-byte input
        output_hash: 32-byte expected output
        iterations: Number of iterations

    Returns:
        True if output matches recomputation
    """
    from hashlib import shake_256

    state = input_hash
    for _ in range(iterations):
        hasher = shake_256(state)
        state = hasher.digest(32)

    return state == output_hash


# Convenience class for VDF with STARK proofs
class VdfWithProof:
    """
    VDF computation with STARK proof generation.

    Example:
        vdf = VdfWithProof()
        result = vdf.compute(input_data)
        # result.output = H^T(input)
        # result.proof = STARK proof (if available)
        # result.checkpoints = intermediate values

        # Later verification
        is_valid = vdf.verify(input_data, result.output, result.proof)
    """

    def __init__(
        self,
        iterations: int = VDF_ITERATIONS,
        checkpoint_interval: int = VDF_CHECKPOINT_INTERVAL,
    ):
        self.iterations = iterations
        self.checkpoint_interval = checkpoint_interval

    def compute(self, input_hash: bytes) -> "VdfComputeResult":
        """
        Compute VDF and generate STARK proof.

        Args:
            input_hash: 32-byte input

        Returns:
            VdfComputeResult with output, checkpoints, and proof
        """
        from hashlib import shake_256

        if len(input_hash) != 32:
            raise ValueError("input_hash must be 32 bytes")

        state = input_hash
        checkpoints = []

        for i in range(self.iterations):
            hasher = shake_256(state)
            state = hasher.digest(32)

            # Save checkpoint
            if (i + 1) % self.checkpoint_interval == 0:
                checkpoints.append(state)

        output_hash = state

        # Generate STARK proof if available
        proof = None
        if STARK_AVAILABLE:
            proof_result = generate_vdf_proof(
                input_hash,
                output_hash,
                checkpoints,
                self.iterations,
            )
            if proof_result:
                proof = proof_result.proof_bytes

        return VdfComputeResult(
            input_hash=input_hash,
            output_hash=output_hash,
            checkpoints=checkpoints,
            proof=proof,
            iterations=self.iterations,
        )

    def verify(
        self,
        input_hash: bytes,
        output_hash: bytes,
        proof: Optional[bytes] = None,
    ) -> bool:
        """
        Verify VDF computation.

        Uses STARK proof if provided and available, otherwise recomputes.

        Args:
            input_hash: 32-byte input
            output_hash: 32-byte claimed output
            proof: Optional STARK proof

        Returns:
            True if valid
        """
        if proof and STARK_AVAILABLE:
            return verify_vdf_proof(
                input_hash,
                output_hash,
                proof,
                self.iterations,
            )

        # Fallback to recomputation
        return verify_vdf_by_recomputation(
            input_hash,
            output_hash,
            self.iterations,
        )


@dataclass
class VdfComputeResult:
    """Result of VDF computation with optional proof."""
    input_hash: bytes
    output_hash: bytes
    checkpoints: List[bytes]
    proof: Optional[bytes]
    iterations: int

    @property
    def has_proof(self) -> bool:
        return self.proof is not None

    @property
    def proof_size(self) -> int:
        return len(self.proof) if self.proof else 0
