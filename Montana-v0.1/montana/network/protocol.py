"""
Ɉ Montana Network Protocol v3.1

Protocol definitions per MONTANA_TECHNICAL_SPECIFICATION.md §17.

Protocol version: 8
Default port: 19656
"""

from __future__ import annotations
from enum import IntEnum

from montana.constants import (
    PROTOCOL_VERSION,
    DEFAULT_PORT,
    NETWORK_ID_MAINNET,
    NETWORK_ID_TESTNET,
    MESSAGE_MAGIC_MAINNET,
    MESSAGE_MAGIC_TESTNET,
    SERVICE_FULL_NODE,
    SERVICE_LIGHT_NODE,
    SERVICE_VDF,
    SERVICE_NTP,
    SERVICE_RELAY,
)


class MessageType(IntEnum):
    """
    Network message types per §17.3.

    Categories:
    - Handshake: HELLO, HELLO_ACK
    - Keepalive: PING, PONG
    - Address: ADDR, GETADDR
    - Inventory: INV, GETDATA, NOTFOUND
    - Blocks: BLOCK, HEADERS, GETHEADERS, GETBLOCKS
    - Heartbeats: HEARTBEAT
    - Transactions: TX, MEMPOOL
    - VDF: VDF_CHECKPOINT
    """
    # Handshake
    HELLO = 0x01
    HELLO_ACK = 0x02

    # Keepalive
    PING = 0x10
    PONG = 0x11

    # Address relay
    ADDR = 0x20
    GETADDR = 0x21

    # Inventory
    INV = 0x30
    GETDATA = 0x31
    NOTFOUND = 0x32

    # Blocks
    BLOCK = 0x40
    HEADERS = 0x41
    GETHEADERS = 0x42
    GETBLOCKS = 0x43

    # Heartbeats
    HEARTBEAT = 0x50

    # Transactions
    TX = 0x60
    MEMPOOL = 0x61

    # VDF
    VDF_CHECKPOINT = 0x70

    # Reject
    REJECT = 0xFF


class InventoryType(IntEnum):
    """Inventory object types."""
    TX = 1
    BLOCK = 2
    HEARTBEAT = 3
    VDF_PROOF = 4


class RejectCode(IntEnum):
    """Rejection reason codes."""
    MALFORMED = 0x01
    INVALID = 0x10
    OBSOLETE = 0x11
    DUPLICATE = 0x12
    NONSTANDARD = 0x40
    DUST = 0x41
    INSUFFICIENTFEE = 0x42
    CHECKPOINT = 0x43


class ServiceFlags:
    """Service capability flags."""
    FULL_NODE = SERVICE_FULL_NODE
    LIGHT_NODE = SERVICE_LIGHT_NODE
    VDF = SERVICE_VDF
    NTP = SERVICE_NTP
    RELAY = SERVICE_RELAY

    # Aliases
    NODE_NETWORK = FULL_NODE
    NODE_VDF = VDF
    NODE_NTP = NTP

    @classmethod
    def has_flag(cls, services: int, flag: int) -> bool:
        """Check if services has flag set."""
        return (services & flag) == flag

    @classmethod
    def to_list(cls, services: int) -> list:
        """Convert service flags to list of names."""
        flags = []
        if cls.has_flag(services, cls.FULL_NODE):
            flags.append("FULL_NODE")
        if cls.has_flag(services, cls.LIGHT_NODE):
            flags.append("LIGHT_NODE")
        if cls.has_flag(services, cls.VDF):
            flags.append("VDF")
        if cls.has_flag(services, cls.NTP):
            flags.append("NTP")
        if cls.has_flag(services, cls.RELAY):
            flags.append("RELAY")
        return flags


def get_network_magic(mainnet: bool = True) -> bytes:
    """Get network magic bytes."""
    return MESSAGE_MAGIC_MAINNET if mainnet else MESSAGE_MAGIC_TESTNET


def get_network_id(mainnet: bool = True) -> int:
    """Get network ID."""
    return NETWORK_ID_MAINNET if mainnet else NETWORK_ID_TESTNET
