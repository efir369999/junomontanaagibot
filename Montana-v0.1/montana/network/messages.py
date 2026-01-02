"""
Ɉ Montana Network Messages v3.1

Message structures per MONTANA_TECHNICAL_SPECIFICATION.md §17.5.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from montana.constants import (
    MESSAGE_MAGIC_MAINNET,
    MESSAGE_HEADER_SIZE,
    MAX_MESSAGE_SIZE,
    PROTOCOL_VERSION,
    HELLO_MAX_USER_AGENT_LENGTH,
)
from montana.core.types import Hash
from montana.core.serialization import ByteReader, ByteWriter
from montana.network.protocol import MessageType, InventoryType, ServiceFlags
from montana.crypto.hash import sha3_256


@dataclass
class MessageHeader:
    """
    Message header per §17.5.

    Size: 13 bytes
    - magic: 4 bytes
    - message_type: 1 byte
    - payload_size: 4 bytes
    - checksum: 4 bytes (first 4 bytes of SHA3-256(payload))
    """
    magic: bytes
    message_type: MessageType
    payload_size: int
    checksum: bytes

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_raw(self.magic)
        w.write_u8(self.message_type)
        w.write_u32(self.payload_size)
        w.write_raw(self.checksum)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> Tuple["MessageHeader", int]:
        r = ByteReader(data)
        magic = r.read_fixed_bytes(4)
        message_type = MessageType(r.read_u8())
        payload_size = r.read_u32()
        checksum = r.read_fixed_bytes(4)
        return cls(magic, message_type, payload_size, checksum), MESSAGE_HEADER_SIZE

    @classmethod
    def create(
        cls,
        message_type: MessageType,
        payload: bytes,
        mainnet: bool = True,
    ) -> "MessageHeader":
        """Create header for payload."""
        magic = MESSAGE_MAGIC_MAINNET if mainnet else b"TEST"
        checksum = sha3_256(payload).data[:4]
        return cls(magic, message_type, len(payload), checksum)

    def verify_checksum(self, payload: bytes) -> bool:
        """Verify payload checksum."""
        expected = sha3_256(payload).data[:4]
        return self.checksum == expected


@dataclass
class HelloMessage:
    """
    Hello handshake message per §17.5.1.

    Sent by initiating peer to start connection.
    """
    version: int                    # Protocol version
    services: int                   # Service flags
    timestamp: int                  # Current time (UTC seconds)
    receiver_services: int          # Receiver's expected services
    receiver_ip: bytes              # Receiver's IP (16 bytes, IPv6 format)
    receiver_port: int              # Receiver's port
    sender_services: int            # Sender's services
    sender_ip: bytes                # Sender's IP
    sender_port: int                # Sender's port
    nonce: int                      # Random nonce
    user_agent: str                 # User agent string
    start_height: int               # Sender's best block height
    relay: bool                     # Whether to relay transactions

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u32(self.version)
        w.write_u64(self.services)
        w.write_u64(self.timestamp)
        w.write_u64(self.receiver_services)
        w.write_raw(self.receiver_ip.ljust(16, b'\x00')[:16])
        w.write_u16(self.receiver_port)
        w.write_u64(self.sender_services)
        w.write_raw(self.sender_ip.ljust(16, b'\x00')[:16])
        w.write_u16(self.sender_port)
        w.write_u64(self.nonce)
        ua_bytes = self.user_agent.encode('utf-8')[:HELLO_MAX_USER_AGENT_LENGTH]
        w.write_bytes(ua_bytes)
        w.write_u64(self.start_height)
        w.write_u8(1 if self.relay else 0)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "HelloMessage":
        r = ByteReader(data)
        version = r.read_u32()
        services = r.read_u64()
        timestamp = r.read_u64()
        receiver_services = r.read_u64()
        receiver_ip = r.read_fixed_bytes(16)
        receiver_port = r.read_u16()
        sender_services = r.read_u64()
        sender_ip = r.read_fixed_bytes(16)
        sender_port = r.read_u16()
        nonce = r.read_u64()
        ua_bytes = r.read_bytes()
        user_agent = ua_bytes.decode('utf-8', errors='replace')
        start_height = r.read_u64()
        relay = r.read_u8() != 0
        return cls(
            version, services, timestamp, receiver_services,
            receiver_ip, receiver_port, sender_services,
            sender_ip, sender_port, nonce, user_agent,
            start_height, relay
        )


@dataclass
class HelloAck:
    """
    Hello acknowledgment per §17.5.2.

    Sent in response to Hello to complete handshake.
    """
    nonce: int                      # Echo sender's nonce

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u64(self.nonce)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "HelloAck":
        r = ByteReader(data)
        nonce = r.read_u64()
        return cls(nonce)


@dataclass
class PingMessage:
    """Ping keepalive message."""
    nonce: int

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u64(self.nonce)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "PingMessage":
        r = ByteReader(data)
        return cls(r.read_u64())


@dataclass
class PongMessage:
    """Pong response to ping."""
    nonce: int

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u64(self.nonce)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "PongMessage":
        r = ByteReader(data)
        return cls(r.read_u64())


@dataclass
class InventoryItem:
    """Single inventory item."""
    inv_type: InventoryType
    hash: Hash

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u8(self.inv_type)
        w.write_raw(self.hash.data)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> Tuple["InventoryItem", int]:
        inv_type = InventoryType(data[offset])
        hash_data = data[offset + 1:offset + 33]
        return cls(inv_type, Hash(hash_data)), 33


@dataclass
class InvMessage:
    """Inventory announcement message."""
    items: List[InventoryItem]

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_varint(len(self.items))
        for item in self.items:
            w.write_raw(item.serialize())
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "InvMessage":
        r = ByteReader(data)
        count = r.read_varint()
        items = []
        for _ in range(count):
            item, size = InventoryItem.deserialize(data, r.offset)
            r.offset += size
            items.append(item)
        return cls(items)


@dataclass
class GetDataMessage:
    """Request for inventory items."""
    items: List[InventoryItem]

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_varint(len(self.items))
        for item in self.items:
            w.write_raw(item.serialize())
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "GetDataMessage":
        r = ByteReader(data)
        count = r.read_varint()
        items = []
        for _ in range(count):
            item, size = InventoryItem.deserialize(data, r.offset)
            r.offset += size
            items.append(item)
        return cls(items)


@dataclass
class NetworkAddress:
    """Network address structure."""
    timestamp: int                  # Last seen time
    services: int                   # Service flags
    ip: bytes                       # IP address (16 bytes)
    port: int                       # Port

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_u64(self.timestamp)
        w.write_u64(self.services)
        w.write_raw(self.ip.ljust(16, b'\x00')[:16])
        w.write_u16(self.port)
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> Tuple["NetworkAddress", int]:
        r = ByteReader(data[offset:])
        timestamp = r.read_u64()
        services = r.read_u64()
        ip = r.read_fixed_bytes(16)
        port = r.read_u16()
        return cls(timestamp, services, ip, port), r.offset


@dataclass
class AddrMessage:
    """Address announcement message."""
    addresses: List[NetworkAddress]

    def serialize(self) -> bytes:
        w = ByteWriter()
        w.write_varint(len(self.addresses))
        for addr in self.addresses:
            w.write_raw(addr.serialize())
        return w.to_bytes()

    @classmethod
    def deserialize(cls, data: bytes) -> "AddrMessage":
        r = ByteReader(data)
        count = r.read_varint()
        addresses = []
        for _ in range(count):
            addr, size = NetworkAddress.deserialize(data, r.offset)
            r.offset += size
            addresses.append(addr)
        return cls(addresses)


@dataclass
class GetAddrMessage:
    """Request for addresses."""

    def serialize(self) -> bytes:
        return b""

    @classmethod
    def deserialize(cls, data: bytes) -> "GetAddrMessage":
        return cls()


def create_hello(
    services: int,
    start_height: int,
    user_agent: str = "Montana/0.1.0",
    relay: bool = True,
) -> HelloMessage:
    """Create Hello message with common defaults."""
    import secrets
    return HelloMessage(
        version=PROTOCOL_VERSION,
        services=services,
        timestamp=int(time.time()),
        receiver_services=0,
        receiver_ip=b'\x00' * 16,
        receiver_port=0,
        sender_services=services,
        sender_ip=b'\x00' * 16,
        sender_port=0,
        nonce=secrets.randbelow(2**64),
        user_agent=user_agent,
        start_height=start_height,
        relay=relay,
    )
