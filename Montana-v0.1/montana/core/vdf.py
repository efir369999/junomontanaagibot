"""
Ɉ Montana VDF (Verifiable Delay Function) v3.1

Layer 1: Temporal Proof per MONTANA_TECHNICAL_SPECIFICATION.md §5.

SHAKE256-based VDF with O(log T) verification via STARK proofs.
Target: 2^24 iterations (~2.5 seconds) for soft finality checkpoint.
"""

from __future__ import annotations
import hashlib
import struct
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable

from montana.constants import (
    VDF_HASH_FUNCTION,
    VDF_BASE_ITERATIONS,
    VDF_MAX_ITERATIONS,
    VDF_MIN_ITERATIONS,
    VDF_STARK_CHECKPOINT_INTERVAL,
    VDF_CHECKPOINT_TIME_SEC,
    SHAKE256_OUTPUT_SIZE,
)
from montana.core.types import Hash

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VDFOutput:
    """
    Output of VDF computation per §5.3.

    Contains the result and checkpoints for STARK proof generation.
    """
    input_hash: Hash                          # Original input (32 bytes)
    output_hash: Hash                         # Final output after T iterations
    iterations: int                           # Number of iterations T
    checkpoints: Tuple[Hash, ...] = ()        # Intermediate states for proof
    computation_time_ms: int = 0              # Actual computation time


@dataclass
class VDFProof:
    """
    STARK proof for VDF verification per §5.4.

    Allows O(log T) verification instead of O(T) recomputation.
    """
    input_hash: Hash
    output_hash: Hash
    iterations: int
    proof_data: bytes                         # STARK proof or checkpoint-based proof
    proof_type: str = "checkpoint"            # "stark" or "checkpoint"

    def serialize(self) -> bytes:
        """Serialize proof for transmission."""
        from montana.core.serialization import ByteWriter
        w = ByteWriter()
        w.write_raw(self.input_hash.data)
        w.write_raw(self.output_hash.data)
        w.write_u64(self.iterations)
        w.write_u8(0 if self.proof_type == "stark" else 1)
        w.write_bytes(self.proof_data)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "VDFProof":
        """Deserialize proof from bytes."""
        from montana.core.serialization import ByteReader
        r = ByteReader(data)
        input_hash = Hash(r.read_fixed_bytes(32))
        output_hash = Hash(r.read_fixed_bytes(32))
        iterations = r.read_u64()
        proof_type = "stark" if r.read_u8() == 0 else "checkpoint"
        proof_data = r.read_bytes()
        return cls(input_hash, output_hash, iterations, proof_data, proof_type)


@dataclass
class VDFCheckpointResult:
    """Result of a single VDF checkpoint computation."""
    iterations: int
    output: Hash
    proof: bytes


class SHAKE256VDF:
    """
    SHAKE256-based Verifiable Delay Function per §5.2.

    Computes: output = SHAKE256(SHAKE256(...SHAKE256(input)...))
                                         ^ T iterations

    Properties:
    - Quantum-resistant (SHAKE256 has no known quantum speedup beyond Grover)
    - Strictly sequential (each iteration depends on previous output)
    - Efficiently verifiable via STARK proofs or checkpoint sampling
    """

    STATE_SIZE = SHAKE256_OUTPUT_SIZE  # 32 bytes
    CHECKPOINT_INTERVAL = VDF_STARK_CHECKPOINT_INTERVAL  # 1000 iterations

    def __init__(self):
        self._cached_ips: Optional[float] = None
        self._current_output: Optional[Hash] = None
        self._total_iterations: int = 0
        self._last_proof: bytes = b""

    @property
    def current_output(self) -> Hash:
        """Get current VDF output."""
        return self._current_output or Hash.zero()

    @property
    def total_iterations(self) -> int:
        """Get total iterations computed."""
        return self._total_iterations

    def get_proof(self) -> bytes:
        """Get the last VDF proof."""
        return self._last_proof

    def compute_checkpoint(
        self,
        input_data: bytes | Hash,
        iterations: int = VDF_BASE_ITERATIONS,
    ) -> VDFCheckpointResult:
        """
        Compute a single VDF checkpoint.

        Args:
            input_data: Input seed
            iterations: Number of iterations

        Returns:
            VDFCheckpointResult with output and proof
        """
        result = self.compute(input_data, iterations, collect_checkpoints=True)
        self._current_output = result.output_hash
        self._total_iterations += result.iterations

        # Create simple proof
        proof = self.create_proof(result)
        proof_bytes = proof.serialize()
        self._last_proof = proof_bytes

        return VDFCheckpointResult(
            iterations=result.iterations,
            output=result.output_hash,
            proof=proof_bytes,
        )

    def _shake256_single(self, state: bytes) -> bytes:
        """Single SHAKE256 iteration."""
        return hashlib.shake_256(state).digest(self.STATE_SIZE)

    def compute(
        self,
        input_data: bytes,
        iterations: int = VDF_BASE_ITERATIONS,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        collect_checkpoints: bool = True,
    ) -> VDFOutput:
        """
        Compute SHAKE256 VDF.

        Args:
            input_data: Input seed (hashed to 32 bytes if not already)
            iterations: Number of sequential iterations T (default: 2^24)
            progress_callback: Optional callback(current, total) for progress
            collect_checkpoints: Whether to collect checkpoints for proof

        Returns:
            VDFOutput with result and checkpoints
        """
        if iterations < VDF_MIN_ITERATIONS:
            raise ValueError(f"Iterations {iterations} below minimum {VDF_MIN_ITERATIONS}")
        if iterations > VDF_MAX_ITERATIONS:
            raise ValueError(f"Iterations {iterations} exceeds maximum {VDF_MAX_ITERATIONS}")

        # Normalize input to 32 bytes
        if isinstance(input_data, Hash):
            input_data = input_data.data
        if len(input_data) != 32:
            input_data = hashlib.sha3_256(input_data).digest()

        input_hash = Hash(input_data)
        state = input_data
        checkpoints: List[Hash] = [input_hash] if collect_checkpoints else []

        start_time = time.perf_counter()

        for i in range(iterations):
            # Collect checkpoint at interval boundaries
            if collect_checkpoints and i > 0 and i % self.CHECKPOINT_INTERVAL == 0:
                checkpoints.append(Hash(state))

            # Core VDF computation
            state = self._shake256_single(state)

            # Progress callback
            if progress_callback and i % 100000 == 0:
                progress_callback(i, iterations)

        # Final checkpoint
        if collect_checkpoints:
            checkpoints.append(Hash(state))

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        logger.debug(
            f"VDF computed: {iterations:,} iterations in {elapsed_ms}ms "
            f"({iterations / (elapsed_ms / 1000):.0f} iter/s)"
        )

        return VDFOutput(
            input_hash=input_hash,
            output_hash=Hash(state),
            iterations=iterations,
            checkpoints=tuple(checkpoints),
            computation_time_ms=elapsed_ms,
        )

    def verify_full(self, vdf_output: VDFOutput) -> bool:
        """
        Verify VDF by full recomputation (O(T)).

        This is the fallback when STARK proofs are not available.
        """
        state = vdf_output.input_hash.data
        for _ in range(vdf_output.iterations):
            state = self._shake256_single(state)
        return state == vdf_output.output_hash.data

    def verify_checkpoints(
        self,
        vdf_output: VDFOutput,
        sample_segments: int = 5,
    ) -> bool:
        """
        Verify VDF using checkpoint sampling (faster than full recomputation).

        Randomly samples segments between checkpoints and verifies them.

        Args:
            vdf_output: VDF output with checkpoints
            sample_segments: Number of segments to verify

        Returns:
            True if sampled segments are valid
        """
        checkpoints = vdf_output.checkpoints
        if len(checkpoints) < 2:
            return self.verify_full(vdf_output)

        # Verify first and last checkpoints match
        if checkpoints[0] != vdf_output.input_hash:
            logger.warning("VDF checkpoint 0 doesn't match input")
            return False

        if checkpoints[-1] != vdf_output.output_hash:
            logger.warning("VDF final checkpoint doesn't match output")
            return False

        # Calculate iterations per segment
        num_segments = len(checkpoints) - 1
        iterations_per_segment = vdf_output.iterations // num_segments

        # Sample random segments to verify
        import secrets
        rng = secrets.SystemRandom()
        all_segments = list(range(num_segments))
        rng.shuffle(all_segments)
        segments_to_check = all_segments[:min(sample_segments, num_segments)]

        for seg_idx in segments_to_check:
            start_state = checkpoints[seg_idx].data
            expected_end = checkpoints[seg_idx + 1].data

            # Recompute segment
            state = start_state
            for _ in range(iterations_per_segment):
                state = self._shake256_single(state)

            if state != expected_end:
                logger.warning(f"VDF segment {seg_idx} verification failed")
                return False

        return True

    def create_proof(self, vdf_output: VDFOutput) -> VDFProof:
        """
        Create verifiable proof from VDF output.

        Uses checkpoint-based proof (STARK integration pending).
        """
        # Serialize checkpoints as proof data
        proof_data = bytearray()
        proof_data.extend(b'MONT')  # Magic
        proof_data.extend(struct.pack('<I', len(vdf_output.checkpoints)))
        for cp in vdf_output.checkpoints:
            proof_data.extend(cp.data)

        return VDFProof(
            input_hash=vdf_output.input_hash,
            output_hash=vdf_output.output_hash,
            iterations=vdf_output.iterations,
            proof_data=bytes(proof_data),
            proof_type="checkpoint",
        )

    def verify_proof(self, proof: VDFProof) -> bool:
        """
        Verify VDF proof.

        Args:
            proof: VDF proof to verify

        Returns:
            True if proof is valid
        """
        if proof.proof_type == "stark":
            # STARK verification (placeholder)
            logger.warning("STARK verification not yet implemented")
            return False

        # Checkpoint-based verification
        try:
            data = proof.proof_data
            if data[:4] != b'MONT':
                logger.warning("Invalid proof magic")
                return False

            num_checkpoints = struct.unpack_from('<I', data, 4)[0]
            offset = 8

            checkpoints: List[Hash] = []
            for _ in range(num_checkpoints):
                checkpoints.append(Hash(data[offset:offset + 32]))
                offset += 32

            # Reconstruct VDFOutput and verify
            vdf_output = VDFOutput(
                input_hash=proof.input_hash,
                output_hash=proof.output_hash,
                iterations=proof.iterations,
                checkpoints=tuple(checkpoints),
            )

            return self.verify_checkpoints(vdf_output)

        except Exception as e:
            logger.error(f"Proof verification error: {e}")
            return False

    def calibrate(self, target_seconds: float = VDF_CHECKPOINT_TIME_SEC) -> int:
        """
        Calibrate iterations for target computation time.

        Args:
            target_seconds: Target time in seconds (default: 2.5s)

        Returns:
            Recommended iterations for target time
        """
        # Run sample computation
        test_input = hashlib.sha3_256(b"montana_vdf_calibration").digest()
        sample_iterations = 50000

        state = test_input
        start = time.perf_counter()
        for _ in range(sample_iterations):
            state = self._shake256_single(state)
        elapsed = time.perf_counter() - start

        ips = sample_iterations / elapsed
        self._cached_ips = ips

        recommended = max(VDF_MIN_ITERATIONS, int(ips * target_seconds))

        logger.info(f"VDF calibration: {ips:.0f} iter/sec")
        logger.info(f"  Recommended: {recommended:,} iterations for {target_seconds}s")

        return recommended

    @property
    def iterations_per_second(self) -> float:
        """Get iterations per second (calibrate if not cached)."""
        if self._cached_ips is None:
            self.calibrate()
        return self._cached_ips or 0.0


# Global VDF instance
_vdf: Optional[SHAKE256VDF] = None


def get_vdf() -> SHAKE256VDF:
    """Get or create global VDF instance."""
    global _vdf
    if _vdf is None:
        _vdf = SHAKE256VDF()
    return _vdf


def compute_vdf(
    input_data: bytes,
    iterations: int = VDF_BASE_ITERATIONS,
) -> VDFOutput:
    """Compute VDF using global instance."""
    return get_vdf().compute(input_data, iterations)


def verify_vdf(vdf_output: VDFOutput) -> bool:
    """Verify VDF output using checkpoints."""
    return get_vdf().verify_checkpoints(vdf_output)


def verify_vdf_proof(proof: VDFProof) -> bool:
    """Verify VDF proof."""
    return get_vdf().verify_proof(proof)
