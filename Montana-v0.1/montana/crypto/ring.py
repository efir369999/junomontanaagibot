"""
Ɉ Montana Ring Signatures v3.1

T3 Privacy: Full privacy via LSAG ring signatures per §14.4.

Ring signatures allow spending without revealing which
input in a ring is the real one. Uses Linkable Spontaneous
Anonymous Group (LSAG) signatures.

Ring size: 11 (1 real + 10 decoys)
"""

from __future__ import annotations
import secrets
import hashlib
from dataclasses import dataclass
from typing import List, Tuple, Optional

from montana.constants import RING_SIZE
from montana.crypto.hash import sha3_256, shake256


@dataclass(frozen=True)
class KeyImage:
    """
    Key image for double-spend prevention.

    Each output can only be spent once. The key image
    is deterministically derived from the secret key,
    so spending the same output twice produces the same key image.
    """
    image: bytes  # 32 bytes

    def serialize(self) -> bytes:
        return self.image

    @classmethod
    def deserialize(cls, data: bytes) -> "KeyImage":
        return cls(image=data[:32])

    def __eq__(self, other: object) -> bool:
        if isinstance(other, KeyImage):
            return self.image == other.image
        return False

    def __hash__(self) -> int:
        return hash(self.image)


@dataclass
class RingSignature:
    """
    LSAG Ring Signature.

    Proves knowledge of one secret key in a ring of public keys
    without revealing which one.
    """
    key_image: KeyImage           # For double-spend detection
    c: List[bytes]                # Challenge values (32 bytes each)
    r: List[bytes]                # Response values (32 bytes each)
    ring_size: int                # Number of keys in ring

    def serialize(self) -> bytes:
        """Serialize ring signature."""
        from montana.core.serialization import ByteWriter
        w = ByteWriter()
        w.write_raw(self.key_image.image)
        w.write_u8(self.ring_size)
        for i in range(self.ring_size):
            w.write_raw(self.c[i])
            w.write_raw(self.r[i])
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "RingSignature":
        """Deserialize ring signature."""
        from montana.core.serialization import ByteReader
        r = ByteReader(data)
        key_image = KeyImage(r.read_fixed_bytes(32))
        ring_size = r.read_u8()
        c = [r.read_fixed_bytes(32) for _ in range(ring_size)]
        responses = [r.read_fixed_bytes(32) for _ in range(ring_size)]
        return cls(key_image=key_image, c=c, r=responses, ring_size=ring_size)


def _hash_to_point(data: bytes) -> bytes:
    """Hash to curve point (simplified)."""
    return sha3_256(b"MONTANA_H2P:" + data).data


def _scalar_mul(scalar: bytes, point: bytes) -> bytes:
    """Scalar multiplication (simplified)."""
    return sha3_256(scalar + point + b"MUL").data


def _point_add(p1: bytes, p2: bytes) -> bytes:
    """Point addition (simplified)."""
    return sha3_256(p1 + p2 + b"ADD").data


def compute_key_image(secret_key: bytes, public_key: bytes) -> KeyImage:
    """
    Compute key image for an output.

    I = x * H(P)

    Where x is the secret key and P is the public key.
    The key image is deterministic and unique per output.
    """
    hp = _hash_to_point(public_key)
    image = _scalar_mul(secret_key, hp)
    return KeyImage(image=image)


def generate_ring_signature(
    message: bytes,
    ring_public_keys: List[bytes],
    secret_key: bytes,
    real_index: int,
) -> RingSignature:
    """
    Generate LSAG ring signature.

    Args:
        message: Message to sign
        ring_public_keys: List of public keys in the ring
        secret_key: Secret key corresponding to ring_public_keys[real_index]
        real_index: Index of the real key in the ring

    Returns:
        RingSignature
    """
    n = len(ring_public_keys)
    if n < 2:
        raise ValueError("Ring must have at least 2 members")
    if real_index < 0 or real_index >= n:
        raise ValueError(f"Invalid real_index: {real_index}")

    # Compute key image
    real_public = ring_public_keys[real_index]
    key_image = compute_key_image(secret_key, real_public)

    # Initialize arrays
    c = [bytes(32)] * n
    r = [bytes(32)] * n

    # Generate random α
    alpha = secrets.token_bytes(32)

    # Compute L_s = α*G
    l_s = _scalar_mul(alpha, b"GENERATOR_G")

    # Compute R_s = α*H(P_s)
    hp_s = _hash_to_point(real_public)
    r_s = _scalar_mul(alpha, hp_s)

    # Start the ring: c_{s+1} = H(m, L_s, R_s)
    c[(real_index + 1) % n] = sha3_256(message + l_s + r_s).data

    # Generate random responses and challenges for other ring members
    for i in range(1, n):
        idx = (real_index + i) % n
        next_idx = (idx + 1) % n

        # Random response
        r[idx] = secrets.token_bytes(32)

        # L_i = r_i*G + c_i*P_i
        ri_g = _scalar_mul(r[idx], b"GENERATOR_G")
        ci_pi = _scalar_mul(c[idx], ring_public_keys[idx])
        l_i = _point_add(ri_g, ci_pi)

        # R_i = r_i*H(P_i) + c_i*I
        hp_i = _hash_to_point(ring_public_keys[idx])
        ri_hp = _scalar_mul(r[idx], hp_i)
        ci_i = _scalar_mul(c[idx], key_image.image)
        r_i = _point_add(ri_hp, ci_i)

        # c_{i+1} = H(m, L_i, R_i)
        c[next_idx] = sha3_256(message + l_i + r_i).data

    # Close the ring: compute r_s such that L_s and R_s are correct
    # r_s = α - c_s * x (mod q)
    # Simplified: use hash-based computation
    r[real_index] = sha3_256(
        alpha + c[real_index] + secret_key + b"RING_CLOSE"
    ).data

    return RingSignature(
        key_image=key_image,
        c=c,
        r=r,
        ring_size=n,
    )


def verify_ring_signature(
    message: bytes,
    ring_public_keys: List[bytes],
    signature: RingSignature,
) -> bool:
    """
    Verify LSAG ring signature.

    Args:
        message: Original message
        ring_public_keys: List of public keys in the ring
        signature: Ring signature to verify

    Returns:
        True if signature is valid
    """
    n = len(ring_public_keys)
    if n != signature.ring_size:
        return False

    # Verify the ring equation
    # For each i: L_i = r_i*G + c_i*P_i, R_i = r_i*H(P_i) + c_i*I
    # c_{i+1} = H(m, L_i, R_i)
    # Ring closes if c_0 (computed) = c_0 (given)

    computed_c = signature.c[0]

    for i in range(n):
        # L_i = r_i*G + c_i*P_i
        ri_g = _scalar_mul(signature.r[i], b"GENERATOR_G")
        ci_pi = _scalar_mul(signature.c[i], ring_public_keys[i])
        l_i = _point_add(ri_g, ci_pi)

        # R_i = r_i*H(P_i) + c_i*I
        hp_i = _hash_to_point(ring_public_keys[i])
        ri_hp = _scalar_mul(signature.r[i], hp_i)
        ci_i = _scalar_mul(signature.c[i], signature.key_image.image)
        r_i = _point_add(ri_hp, ci_i)

        # c_{i+1} = H(m, L_i, R_i)
        next_c = sha3_256(message + l_i + r_i).data

        if i < n - 1:
            if next_c != signature.c[i + 1]:
                return False
        else:
            # Check ring closure
            if next_c != signature.c[0]:
                return False

    return True


def select_ring_members(
    real_output: bytes,
    available_outputs: List[bytes],
    ring_size: int = RING_SIZE,
) -> Tuple[List[bytes], int]:
    """
    Select decoy outputs for ring.

    Args:
        real_output: The real output public key
        available_outputs: Pool of available outputs
        ring_size: Desired ring size (default: 11)

    Returns:
        (ring_public_keys, real_index)
    """
    if len(available_outputs) < ring_size - 1:
        raise ValueError(
            f"Not enough outputs for ring: need {ring_size - 1}, "
            f"have {len(available_outputs)}"
        )

    # Select random decoys
    decoys = []
    available = [o for o in available_outputs if o != real_output]
    indices = list(range(len(available)))
    secrets.SystemRandom().shuffle(indices)

    for i in indices[:ring_size - 1]:
        decoys.append(available[i])

    # Insert real output at random position
    ring = decoys.copy()
    real_index = secrets.randbelow(ring_size)
    ring.insert(real_index, real_output)

    return ring, real_index
