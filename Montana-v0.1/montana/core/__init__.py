"""
Ɉ Montana Core Module v3.1

Contains fundamental types, serialization, and layer implementations.
"""

from montana.core.types import (
    Hash,
    PublicKey,
    SecretKey,
    Signature,
    KeyPair,
    NodeType,
    ParticipationTier,
    PrivacyTier,
    HeartbeatSource,
    empty_hash,
    empty_signature,
)

from montana.core.serialization import (
    ByteReader,
    ByteWriter,
    serialize_u8,
    serialize_u16,
    serialize_u32,
    serialize_u64,
    serialize_varint,
    serialize_bytes,
    deserialize_u8,
    deserialize_u16,
    deserialize_u32,
    deserialize_u64,
    deserialize_varint,
    deserialize_bytes,
)

__all__ = [
    # Types
    "Hash",
    "PublicKey",
    "SecretKey",
    "Signature",
    "KeyPair",
    # Enums
    "NodeType",
    "ParticipationTier",
    "PrivacyTier",
    "HeartbeatSource",
    # Helpers
    "empty_hash",
    "empty_signature",
    # Serialization
    "ByteReader",
    "ByteWriter",
    "serialize_u8",
    "serialize_u16",
    "serialize_u32",
    "serialize_u64",
    "serialize_varint",
    "serialize_bytes",
    "deserialize_u8",
    "deserialize_u16",
    "deserialize_u32",
    "deserialize_u64",
    "deserialize_varint",
    "deserialize_bytes",
]
