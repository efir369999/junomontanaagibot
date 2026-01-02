"""
Ɉ Montana Block Structures v3.1

Layer 2: Block and DAG per MONTANA_TECHNICAL_SPECIFICATION.md §9.

Implements DAG-based block structure with:
- BlockHeader (197 bytes fixed)
- Multiple parent references (DAG, not chain)
- VDF checkpoint for temporal ordering
- Merkle roots for heartbeats and transactions
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set

from montana.constants import (
    HASH_SIZE,
    PROTOCOL_VERSION,
    BLOCK_TIME_TARGET_SEC,
    MAX_BLOCK_SIZE,
    MAX_HEARTBEATS_PER_BLOCK,
    MAX_TRANSACTIONS_PER_BLOCK,
    GENESIS_TIMESTAMP_MS,
)
from montana.core.types import Hash, PublicKey, Signature
from montana.core.serialization import ByteReader, ByteWriter
from montana.crypto.hash import sha3_256, HashBuilder


@dataclass
class BlockHeader:
    """
    Block header per §9.1.

    Fixed size: 197 bytes (excluding parent hashes)

    Structure:
    - version: 1 byte
    - timestamp_ms: 8 bytes
    - height: 8 bytes
    - parent_count: 1 byte
    - parent_hashes: 32 * parent_count bytes (variable, typically 1-3)
    - vdf_output: 32 bytes
    - vdf_iterations: 8 bytes
    - heartbeat_root: 32 bytes
    - tx_root: 32 bytes
    - state_root: 32 bytes
    - producer_id: 32 bytes
    - nonce: 8 bytes
    """
    version: int                          # Protocol version (1 byte)
    timestamp_ms: int                     # Block timestamp UTC (8 bytes)
    height: int                           # Block height (8 bytes)
    parent_hashes: Tuple[Hash, ...]       # DAG parent references (variable)
    vdf_output: Hash                      # VDF checkpoint output (32 bytes)
    vdf_iterations: int                   # VDF iterations since last block (8 bytes)
    heartbeat_root: Hash                  # Merkle root of heartbeats (32 bytes)
    tx_root: Hash                         # Merkle root of transactions (32 bytes)
    state_root: Hash                      # State root after block (32 bytes)
    producer_id: Hash                     # Block producer node ID (32 bytes)
    nonce: int                            # Random nonce for uniqueness (8 bytes)

    # Computed
    _hash: Optional[Hash] = field(default=None, repr=False, compare=False)

    @property
    def parent_count(self) -> int:
        return len(self.parent_hashes)

    @property
    def is_genesis(self) -> bool:
        return self.height == 0 and len(self.parent_hashes) == 0

    def hash(self) -> Hash:
        """Compute block header hash (cached)."""
        if self._hash is None:
            object.__setattr__(self, '_hash', sha3_256(self.serialize()))
        return self._hash

    def serialize(self) -> bytes:
        """Serialize block header."""
        w = ByteWriter()
        w.write_u8(self.version)
        w.write_u64(self.timestamp_ms)
        w.write_u64(self.height)
        w.write_u8(len(self.parent_hashes))
        for parent in self.parent_hashes:
            w.write_raw(parent.data)
        w.write_raw(self.vdf_output.data)
        w.write_u64(self.vdf_iterations)
        w.write_raw(self.heartbeat_root.data)
        w.write_raw(self.tx_root.data)
        w.write_raw(self.state_root.data)
        w.write_raw(self.producer_id.data)
        w.write_u64(self.nonce)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["BlockHeader", int]:
        """Deserialize block header from bytes."""
        r = ByteReader(data)

        version = r.read_u8()
        timestamp_ms = r.read_u64()
        height = r.read_u64()
        parent_count = r.read_u8()

        parent_hashes = tuple(
            Hash(r.read_fixed_bytes(HASH_SIZE))
            for _ in range(parent_count)
        )

        vdf_output = Hash(r.read_fixed_bytes(HASH_SIZE))
        vdf_iterations = r.read_u64()
        heartbeat_root = Hash(r.read_fixed_bytes(HASH_SIZE))
        tx_root = Hash(r.read_fixed_bytes(HASH_SIZE))
        state_root = Hash(r.read_fixed_bytes(HASH_SIZE))
        producer_id = Hash(r.read_fixed_bytes(HASH_SIZE))
        nonce = r.read_u64()

        header = cls(
            version=version,
            timestamp_ms=timestamp_ms,
            height=height,
            parent_hashes=parent_hashes,
            vdf_output=vdf_output,
            vdf_iterations=vdf_iterations,
            heartbeat_root=heartbeat_root,
            tx_root=tx_root,
            state_root=state_root,
            producer_id=producer_id,
            nonce=nonce,
        )

        return header, r.offset

    @property
    def serialized_size(self) -> int:
        """Calculate serialized size."""
        # Fixed: 1 + 8 + 8 + 1 + 32 + 8 + 32 + 32 + 32 + 32 + 8 = 194
        # Variable: 32 * parent_count
        return 194 + 32 * len(self.parent_hashes)


@dataclass
class Block:
    """
    Complete block with header and body per §9.

    Contains:
    - Header with metadata
    - List of heartbeats
    - List of transactions
    - Producer signature
    """
    header: BlockHeader
    heartbeats: List[bytes]              # Serialized heartbeats
    transactions: List[bytes]            # Serialized transactions
    signature: Signature                 # Producer's signature on header

    # Computed
    _hash: Optional[Hash] = field(default=None, repr=False, compare=False)

    def hash(self) -> Hash:
        """Block hash is header hash."""
        return self.header.hash()

    @property
    def height(self) -> int:
        return self.header.height

    @property
    def timestamp_ms(self) -> int:
        return self.header.timestamp_ms

    @property
    def parent_hashes(self) -> Tuple[Hash, ...]:
        return self.header.parent_hashes

    @property
    def is_genesis(self) -> bool:
        return self.header.is_genesis

    def serialize(self) -> bytes:
        """Serialize complete block."""
        w = ByteWriter()

        # Header
        header_bytes = self.header.serialize()
        w.write_bytes(header_bytes)

        # Heartbeats
        w.write_varint(len(self.heartbeats))
        for hb in self.heartbeats:
            w.write_bytes(hb)

        # Transactions
        w.write_varint(len(self.transactions))
        for tx in self.transactions:
            w.write_bytes(tx)

        # Signature
        w.write_raw(self.signature.serialize())

        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["Block", int]:
        """Deserialize block from bytes."""
        r = ByteReader(data)

        # Header
        header_bytes = r.read_bytes()
        header, _ = BlockHeader.deserialize(header_bytes)

        # Heartbeats
        heartbeat_count = r.read_varint()
        heartbeats = [r.read_bytes() for _ in range(heartbeat_count)]

        # Transactions
        tx_count = r.read_varint()
        transactions = [r.read_bytes() for _ in range(tx_count)]

        # Signature
        sig, _ = Signature.deserialize(data, r.offset)
        r.offset += 1 + 17088  # Algorithm byte + signature

        block = cls(
            header=header,
            heartbeats=heartbeats,
            transactions=transactions,
            signature=sig,
        )

        return block, r.offset

    def validate_structure(self) -> Tuple[bool, Optional[str]]:
        """
        Validate block structure (not consensus rules).

        Returns:
            (is_valid, error_message)
        """
        # Check heartbeat count
        if len(self.heartbeats) > MAX_HEARTBEATS_PER_BLOCK:
            return False, f"Too many heartbeats: {len(self.heartbeats)} > {MAX_HEARTBEATS_PER_BLOCK}"

        # Check transaction count
        if len(self.transactions) > MAX_TRANSACTIONS_PER_BLOCK:
            return False, f"Too many transactions: {len(self.transactions)} > {MAX_TRANSACTIONS_PER_BLOCK}"

        # Check total size
        size = len(self.serialize())
        if size > MAX_BLOCK_SIZE:
            return False, f"Block too large: {size} > {MAX_BLOCK_SIZE}"

        # Check parent count (DAG allows multiple parents)
        if not self.is_genesis and len(self.parent_hashes) == 0:
            return False, "Non-genesis block must have at least one parent"

        return True, None


def compute_merkle_root(items: List[bytes]) -> Hash:
    """
    Compute Merkle root of items.

    Uses SHA3-256 for internal nodes.
    """
    if not items:
        return Hash.zero()

    # Hash all items
    hashes = [sha3_256(item) for item in items]

    # Build tree
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])  # Duplicate last if odd

        next_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i].data + hashes[i + 1].data
            next_level.append(sha3_256(combined))
        hashes = next_level

    return hashes[0]


def create_genesis_block(
    producer_id: Hash,
    initial_vdf_output: Hash,
) -> Block:
    """
    Create the genesis block.

    The genesis block has:
    - Height 0
    - No parents
    - Genesis timestamp
    - Empty heartbeats and transactions
    """
    header = BlockHeader(
        version=PROTOCOL_VERSION,
        timestamp_ms=GENESIS_TIMESTAMP_MS,
        height=0,
        parent_hashes=(),
        vdf_output=initial_vdf_output,
        vdf_iterations=0,
        heartbeat_root=Hash.zero(),
        tx_root=Hash.zero(),
        state_root=Hash.zero(),
        producer_id=producer_id,
        nonce=0,
    )

    return Block(
        header=header,
        heartbeats=[],
        transactions=[],
        signature=Signature.empty(),
    )


def create_block(
    parent_hashes: List[Hash],
    height: int,
    producer_id: Hash,
    vdf_output: Hash,
    vdf_iterations: int,
    heartbeats: List[bytes],
    transactions: List[bytes],
    state_root: Hash,
    nonce: int = 0,
) -> Block:
    """
    Create a new block (unsigned).

    Args:
        parent_hashes: DAG parent block hashes
        height: Block height
        producer_id: Producer node ID
        vdf_output: Current VDF checkpoint
        vdf_iterations: VDF iterations since parent
        heartbeats: Serialized heartbeats
        transactions: Serialized transactions
        state_root: State root after applying block
        nonce: Optional nonce

    Returns:
        Unsigned block ready for signing
    """
    import secrets

    heartbeat_root = compute_merkle_root(heartbeats)
    tx_root = compute_merkle_root(transactions)

    header = BlockHeader(
        version=PROTOCOL_VERSION,
        timestamp_ms=int(time.time() * 1000),
        height=height,
        parent_hashes=tuple(parent_hashes),
        vdf_output=vdf_output,
        vdf_iterations=vdf_iterations,
        heartbeat_root=heartbeat_root,
        tx_root=tx_root,
        state_root=state_root,
        producer_id=producer_id,
        nonce=nonce or secrets.randbelow(2**64),
    )

    return Block(
        header=header,
        heartbeats=heartbeats,
        transactions=transactions,
        signature=Signature.empty(),
    )


def sign_block(block: Block, secret_key) -> Block:
    """
    Sign a block with the producer's secret key.

    Args:
        block: Block to sign
        secret_key: Producer's SecretKey

    Returns:
        New block with signature set
    """
    from montana.crypto.sphincs import sphincs_sign
    from dataclasses import replace

    header_bytes = block.header.serialize()
    signature = sphincs_sign(secret_key, header_bytes)

    return replace(block, signature=signature)


def verify_block_signature(block: Block, public_key: PublicKey) -> bool:
    """
    Verify block producer signature.

    Args:
        block: Block to verify
        public_key: Producer's public key

    Returns:
        True if signature is valid
    """
    from montana.crypto.sphincs import sphincs_verify

    header_bytes = block.header.serialize()
    return sphincs_verify(public_key, header_bytes, block.signature)
