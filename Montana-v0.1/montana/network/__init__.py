"""
Ɉ Montana Network Module v3.1

P2P networking per MONTANA_TECHNICAL_SPECIFICATION.md §17.
"""

from montana.network.protocol import (
    MessageType,
    InventoryType,
    ServiceFlags,
    PROTOCOL_VERSION,
)
from montana.network.messages import (
    MessageHeader,
    HelloMessage,
    HelloAck,
    PingMessage,
    PongMessage,
    InvMessage,
    GetDataMessage,
)
from montana.network.peer import (
    Peer,
    PeerState,
    PeerInfo,
    PeerManager,
    DisconnectReason,
)
from montana.network.handshake import (
    HandshakeProtocol,
    HandshakeResult,
    perform_handshake,
)
from montana.network.bootstrap import (
    BootstrapNode,
    BootstrapManager,
    OFFICIAL_BOOTSTRAP_NODES,
    get_bootstrap_addresses,
)
from montana.network.sync import (
    SyncState,
    SyncProgress,
    SyncManager,
)

__all__ = [
    # Protocol
    "MessageType",
    "InventoryType",
    "ServiceFlags",
    "PROTOCOL_VERSION",
    # Messages
    "MessageHeader",
    "HelloMessage",
    "HelloAck",
    "PingMessage",
    "PongMessage",
    "InvMessage",
    "GetDataMessage",
    # Peer
    "Peer",
    "PeerState",
    "PeerInfo",
    "PeerManager",
    "DisconnectReason",
    # Handshake
    "HandshakeProtocol",
    "HandshakeResult",
    "perform_handshake",
    # Bootstrap
    "BootstrapNode",
    "BootstrapManager",
    "OFFICIAL_BOOTSTRAP_NODES",
    "get_bootstrap_addresses",
    # Sync
    "SyncState",
    "SyncProgress",
    "SyncManager",
]
