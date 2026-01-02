"""
Ɉ Montana Protocol Types v3.1

Core cryptographic types and protocol enums per MONTANA_TECHNICAL_SPECIFICATION.md.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
import hashlib

from montana.constants import (
    HASH_SIZE,
    SPHINCS_PUBLIC_KEY_SIZE,
    SPHINCS_SECRET_KEY_SIZE,
    SPHINCS_SIGNATURE_SIZE,
    ALGORITHM_SPHINCS_PLUS,
    BIG_ENDIAN,
    NODE_TYPE_FULL,
    NODE_TYPE_LIGHT,
    TIER_1,
    TIER_2,
    TIER_3,
    PRIVACY_T0,
    PRIVACY_T1,
    PRIVACY_T2,
    PRIVACY_T3,
)


# ==============================================================================
# NODE TYPES (§1.3.1)
# ==============================================================================
class NodeType(IntEnum):
    """
    Montana node types per §1.3.1.

    FULL (1): Full history + VDF computation 
    LIGHT (2): History from connection time only
    """
    FULL = NODE_TYPE_FULL    # Type 1: Full Node
    LIGHT = NODE_TYPE_LIGHT  # Type 2: Light Node


# ==============================================================================
# PARTICIPATION TIERS (§1.3.2)
# ==============================================================================
class ParticipationTier(IntEnum):
    """
    Participation tiers for lottery eligibility per §1.3.2.

    Lottery weights:
      Tier 1: 70% → Full Node operators
      Tier 2: 20% → Light Node operators OR TG Bot/Channel owners
      Tier 3: 10% → TG Community participants
    """
    TIER_1 = TIER_1  # Full Node operators
    TIER_2 = TIER_2  # Light Node / TG Bot owners
    TIER_3 = TIER_3  # TG Community users


# ==============================================================================
# PRIVACY TIERS (§14)
# ==============================================================================
class PrivacyTier(IntEnum):
    """
    Transaction privacy tiers per §14.

    T0: Transparent (fee multiplier 1x)
    T1: Hidden receiver via stealth address (fee multiplier 2x)
    T2: Hidden receiver + amount via Pedersen (fee multiplier 5x)
    T3: Fully private via ring signature (fee multiplier 10x)
    """
    T0 = PRIVACY_T0  # Transparent
    T1 = PRIVACY_T1  # Stealth address
    T2 = PRIVACY_T2  # Stealth + Pedersen
    T3 = PRIVACY_T3  # Full privacy (ring sig)


# ==============================================================================
# HEARTBEAT SOURCES (§7)
# ==============================================================================
class HeartbeatSource(IntEnum):
    """
    Source types for heartbeat generation per §7.

    Each source maps to a participation tier:
      FULL_NODE → Tier 1
      LIGHT_NODE → Tier 2
      TELEGRAM_BOT → Tier 2
      TELEGRAM_USER → Tier 3
    """
    FULL_NODE = 1      # Full Node heartbeat → Tier 1
    LIGHT_NODE = 2     # Light Node heartbeat → Tier 2
    TELEGRAM_BOT = 3   # TG Bot owner → Tier 2
    TELEGRAM_USER = 4  # TG Community user → Tier 3

    def to_tier(self) -> ParticipationTier:
        """Map heartbeat source to participation tier."""
        if self == HeartbeatSource.FULL_NODE:
            return ParticipationTier.TIER_1
        elif self in (HeartbeatSource.LIGHT_NODE, HeartbeatSource.TELEGRAM_BOT):
            return ParticipationTier.TIER_2
        else:
            return ParticipationTier.TIER_3


# ==============================================================================
# HASH TYPE
# ==============================================================================
@dataclass(frozen=True, slots=True)
class Hash:
    """
    SHA3-256 hash output.

    SIZE: 32 bytes
    SERIALIZATION: raw bytes
    """
    data: bytes = field(default_factory=lambda: bytes(HASH_SIZE))

    def __post_init__(self):
        if len(self.data) != HASH_SIZE:
            raise ValueError(f"Hash must be {HASH_SIZE} bytes, got {len(self.data)}")

    def __bytes__(self) -> bytes:
        return self.data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Hash):
            return self.data == other.data
        if isinstance(other, bytes):
            return self.data == other
        return False

    def __hash__(self) -> int:
        return hash(self.data)

    def __repr__(self) -> str:
        return f"Hash({self.data.hex()[:16]}...)"

    def hex(self) -> str:
        return self.data.hex()

    @classmethod
    def from_hex(cls, hex_string: str) -> Hash:
        return cls(bytes.fromhex(hex_string))

    @classmethod
    def zero(cls) -> Hash:
        return cls(bytes(HASH_SIZE))

    @classmethod
    def from_bytes(cls, data: bytes) -> Hash:
        return cls(data)

    def serialize(self) -> bytes:
        """Serialize to raw bytes."""
        return self.data

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> tuple[Hash, int]:
        """Deserialize from bytes, return (Hash, bytes_consumed)."""
        return cls(data[offset:offset + HASH_SIZE]), HASH_SIZE


# ==============================================================================
# PUBLIC KEY TYPE
# ==============================================================================
@dataclass(frozen=True, slots=True)
class PublicKey:
    """
    Public key with algorithm identifier.

    SIZE: 33 bytes (algorithm: 1 byte, data: 32 bytes)
    SERIALIZATION: algorithm || data
    """
    algorithm: int = ALGORITHM_SPHINCS_PLUS
    data: bytes = field(default_factory=lambda: bytes(SPHINCS_PUBLIC_KEY_SIZE))

    def __post_init__(self):
        if len(self.data) != SPHINCS_PUBLIC_KEY_SIZE:
            raise ValueError(
                f"PublicKey data must be {SPHINCS_PUBLIC_KEY_SIZE} bytes, got {len(self.data)}"
            )

    def __bytes__(self) -> bytes:
        return bytes([self.algorithm]) + self.data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PublicKey):
            return self.algorithm == other.algorithm and self.data == other.data
        return False

    def __hash__(self) -> int:
        return hash((self.algorithm, self.data))

    def __repr__(self) -> str:
        return f"PublicKey(alg={self.algorithm}, data={self.data.hex()[:16]}...)"

    def hex(self) -> str:
        return bytes(self).hex()

    @classmethod
    def from_hex(cls, hex_string: str) -> PublicKey:
        data = bytes.fromhex(hex_string)
        return cls(algorithm=data[0], data=data[1:])

    def serialize(self) -> bytes:
        """Serialize to bytes: algorithm || data."""
        return bytes([self.algorithm]) + self.data

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> tuple[PublicKey, int]:
        """Deserialize from bytes, return (PublicKey, bytes_consumed)."""
        algorithm = data[offset]
        key_data = data[offset + 1:offset + 1 + SPHINCS_PUBLIC_KEY_SIZE]
        return cls(algorithm=algorithm, data=key_data), 1 + SPHINCS_PUBLIC_KEY_SIZE

    def to_address(self) -> Hash:
        """Derive address (hash of public key)."""
        return Hash(hashlib.sha3_256(bytes(self)).digest())


# ==============================================================================
# SECRET KEY TYPE
# ==============================================================================
@dataclass(frozen=True, slots=True)
class SecretKey:
    """
    Secret key with algorithm identifier.

    SIZE: 65 bytes (algorithm: 1 byte, data: 64 bytes)
    NOTE: Never transmitted over network.
    """
    algorithm: int = ALGORITHM_SPHINCS_PLUS
    data: bytes = field(default_factory=lambda: bytes(SPHINCS_SECRET_KEY_SIZE))

    def __post_init__(self):
        if len(self.data) != SPHINCS_SECRET_KEY_SIZE:
            raise ValueError(
                f"SecretKey data must be {SPHINCS_SECRET_KEY_SIZE} bytes, got {len(self.data)}"
            )

    def __bytes__(self) -> bytes:
        return bytes([self.algorithm]) + self.data

    def __repr__(self) -> str:
        # Never expose secret key data
        return f"SecretKey(alg={self.algorithm}, data=<redacted>)"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretKey):
            return self.algorithm == other.algorithm and self.data == other.data
        return False

    def __hash__(self) -> int:
        return hash((self.algorithm, self.data))

    def serialize(self) -> bytes:
        """Serialize to bytes: algorithm || data. Use with caution!"""
        return bytes([self.algorithm]) + self.data

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> tuple[SecretKey, int]:
        """Deserialize from bytes, return (SecretKey, bytes_consumed)."""
        algorithm = data[offset]
        key_data = data[offset + 1:offset + 1 + SPHINCS_SECRET_KEY_SIZE]
        return cls(algorithm=algorithm, data=key_data), 1 + SPHINCS_SECRET_KEY_SIZE


# ==============================================================================
# SIGNATURE TYPE
# ==============================================================================
@dataclass(frozen=True, slots=True)
class Signature:
    """
    Cryptographic signature with algorithm identifier.

    SIZE: 17089 bytes (algorithm: 1 byte, data: 17088 bytes for SPHINCS+-SHAKE-128f)
    SERIALIZATION: algorithm || data
    """
    algorithm: int = ALGORITHM_SPHINCS_PLUS
    data: bytes = field(default_factory=lambda: bytes(SPHINCS_SIGNATURE_SIZE))

    def __post_init__(self):
        if len(self.data) != SPHINCS_SIGNATURE_SIZE:
            raise ValueError(
                f"Signature data must be {SPHINCS_SIGNATURE_SIZE} bytes, got {len(self.data)}"
            )

    def __bytes__(self) -> bytes:
        return bytes([self.algorithm]) + self.data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Signature):
            return self.algorithm == other.algorithm and self.data == other.data
        return False

    def __hash__(self) -> int:
        return hash((self.algorithm, self.data))

    def __repr__(self) -> str:
        return f"Signature(alg={self.algorithm}, data={self.data.hex()[:16]}...)"

    def hex(self) -> str:
        return bytes(self).hex()

    @classmethod
    def empty(cls) -> Signature:
        """Create an empty signature (for signing preparation)."""
        return cls(algorithm=ALGORITHM_SPHINCS_PLUS, data=bytes(SPHINCS_SIGNATURE_SIZE))

    def serialize(self) -> bytes:
        """Serialize to bytes: algorithm || data."""
        return bytes([self.algorithm]) + self.data

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> tuple[Signature, int]:
        """Deserialize from bytes, return (Signature, bytes_consumed)."""
        algorithm = data[offset]
        sig_data = data[offset + 1:offset + 1 + SPHINCS_SIGNATURE_SIZE]
        return cls(algorithm=algorithm, data=sig_data), 1 + SPHINCS_SIGNATURE_SIZE


# ==============================================================================
# KEY PAIR TYPE
# ==============================================================================
@dataclass(frozen=True, slots=True)
class KeyPair:
    """
    Public/Secret key pair for signing operations.
    """
    public: PublicKey
    secret: SecretKey

    def __post_init__(self):
        if self.public.algorithm != self.secret.algorithm:
            raise ValueError("PublicKey and SecretKey must use same algorithm")

    def __repr__(self) -> str:
        return f"KeyPair(public={self.public})"

    @property
    def algorithm(self) -> int:
        return self.public.algorithm

    def to_address(self) -> Hash:
        """Derive address from public key."""
        return self.public.to_address()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def empty_hash() -> Hash:
    """Create a zeroed hash (for initialization)."""
    return Hash.zero()


def empty_signature() -> Signature:
    """Create an empty signature (for signing preparation)."""
    return Signature.empty()
