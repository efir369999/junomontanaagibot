"""
Ɉ Montana Peer Management v3.1

Peer connection and management per MONTANA_TECHNICAL_SPECIFICATION.md §17.
"""

from __future__ import annotations
import asyncio
import time
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Callable, Any
from enum import IntEnum, auto

from montana.constants import (
    PROTOCOL_VERSION,
    DEFAULT_PORT,
    MAX_PEERS,
    MAX_INBOUND_PEERS,
    MAX_OUTBOUND_PEERS,
    PEER_HANDSHAKE_TIMEOUT_SEC,
    PEER_PING_INTERVAL_SEC,
    PEER_TIMEOUT_SEC,
    MESSAGE_HEADER_SIZE,
    MAX_MESSAGE_SIZE,
    MESSAGE_MAGIC_MAINNET,
)
from montana.core.types import Hash
from montana.network.protocol import MessageType, ServiceFlags
from montana.network.messages import (
    MessageHeader,
    HelloMessage,
    HelloAck,
    PingMessage,
    PongMessage,
    create_hello,
)
from montana.crypto.hash import sha3_256


class PeerState(IntEnum):
    """Peer connection state."""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    HANDSHAKING = 3
    READY = 4
    DISCONNECTING = 5


class DisconnectReason(IntEnum):
    """Reason for peer disconnection."""
    NONE = 0
    REQUESTED = 1
    TIMEOUT = 2
    PROTOCOL_ERROR = 3
    INCOMPATIBLE_VERSION = 4
    DUPLICATE_CONNECTION = 5
    TOO_MANY_PEERS = 6
    BANNED = 7
    SELF_CONNECTION = 8
    PING_TIMEOUT = 9


@dataclass
class PeerInfo:
    """Information about a peer."""
    address: Tuple[str, int]
    services: int = 0
    version: int = 0
    user_agent: str = ""
    start_height: int = 0
    last_seen: float = 0.0
    latency_ms: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    is_inbound: bool = False

    @property
    def ip(self) -> str:
        return self.address[0]

    @property
    def port(self) -> int:
        return self.address[1]


@dataclass
class Peer:
    """
    Represents a connected peer.

    Handles connection state, message framing, and protocol handshake.
    """
    address: Tuple[str, int]
    is_inbound: bool
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    state: PeerState = PeerState.DISCONNECTED
    info: PeerInfo = field(default_factory=lambda: PeerInfo(("", 0)))

    # Handshake
    local_nonce: int = field(default_factory=lambda: secrets.randbelow(2**64))
    remote_nonce: int = 0
    handshake_complete: bool = False

    # Timing
    connect_time: float = 0.0
    last_send: float = 0.0
    last_recv: float = 0.0
    last_ping: float = 0.0
    pending_ping_nonce: Optional[int] = None

    # Disconnect
    disconnect_reason: DisconnectReason = DisconnectReason.NONE

    # Message handlers
    _message_handlers: Dict[MessageType, Callable] = field(default_factory=dict)

    def __post_init__(self):
        self.info = PeerInfo(self.address, is_inbound=self.is_inbound)

    @property
    def is_connected(self) -> bool:
        return self.state in (PeerState.CONNECTED, PeerState.HANDSHAKING, PeerState.READY)

    @property
    def is_ready(self) -> bool:
        return self.state == PeerState.READY and self.handshake_complete

    async def connect(self, timeout: float = PEER_HANDSHAKE_TIMEOUT_SEC) -> bool:
        """
        Establish connection to peer.

        Returns:
            True if connection successful
        """
        if self.is_inbound:
            return False  # Inbound connections are already established

        self.state = PeerState.CONNECTING

        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.address[0], self.address[1]),
                timeout=timeout
            )
            self.state = PeerState.CONNECTED
            self.connect_time = time.time()
            return True
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError) as e:
            self.state = PeerState.DISCONNECTED
            self.disconnect_reason = DisconnectReason.TIMEOUT
            return False

    async def disconnect(self, reason: DisconnectReason = DisconnectReason.REQUESTED):
        """Disconnect from peer."""
        self.disconnect_reason = reason
        self.state = PeerState.DISCONNECTING

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

        self.reader = None
        self.writer = None
        self.state = PeerState.DISCONNECTED

    async def send_message(
        self,
        message_type: MessageType,
        payload: bytes,
        mainnet: bool = True,
    ) -> bool:
        """
        Send a message to peer.

        Args:
            message_type: Type of message
            payload: Serialized message payload
            mainnet: Whether to use mainnet magic

        Returns:
            True if sent successfully
        """
        if not self.writer or self.state == PeerState.DISCONNECTED:
            return False

        header = MessageHeader.create(message_type, payload, mainnet)
        message = header.serialize() + payload

        try:
            self.writer.write(message)
            await self.writer.drain()

            self.last_send = time.time()
            self.info.bytes_sent += len(message)
            self.info.messages_sent += 1

            return True
        except Exception:
            await self.disconnect(DisconnectReason.PROTOCOL_ERROR)
            return False

    async def receive_message(
        self,
        timeout: Optional[float] = None,
    ) -> Optional[Tuple[MessageType, bytes]]:
        """
        Receive a message from peer.

        Args:
            timeout: Optional read timeout

        Returns:
            (message_type, payload) or None on error
        """
        if not self.reader or self.state == PeerState.DISCONNECTED:
            return None

        try:
            # Read header
            if timeout:
                header_data = await asyncio.wait_for(
                    self.reader.readexactly(MESSAGE_HEADER_SIZE),
                    timeout=timeout
                )
            else:
                header_data = await self.reader.readexactly(MESSAGE_HEADER_SIZE)

            header, _ = MessageHeader.deserialize(header_data)

            # Validate magic
            if header.magic != MESSAGE_MAGIC_MAINNET:
                await self.disconnect(DisconnectReason.PROTOCOL_ERROR)
                return None

            # Validate size
            if header.payload_size > MAX_MESSAGE_SIZE:
                await self.disconnect(DisconnectReason.PROTOCOL_ERROR)
                return None

            # Read payload
            if header.payload_size > 0:
                if timeout:
                    payload = await asyncio.wait_for(
                        self.reader.readexactly(header.payload_size),
                        timeout=timeout
                    )
                else:
                    payload = await self.reader.readexactly(header.payload_size)
            else:
                payload = b""

            # Verify checksum
            if not header.verify_checksum(payload):
                await self.disconnect(DisconnectReason.PROTOCOL_ERROR)
                return None

            self.last_recv = time.time()
            self.info.last_seen = self.last_recv
            self.info.bytes_received += MESSAGE_HEADER_SIZE + header.payload_size
            self.info.messages_received += 1

            return (header.message_type, payload)

        except asyncio.TimeoutError:
            return None
        except asyncio.IncompleteReadError:
            await self.disconnect(DisconnectReason.TIMEOUT)
            return None
        except Exception:
            await self.disconnect(DisconnectReason.PROTOCOL_ERROR)
            return None

    async def send_hello(
        self,
        services: int,
        start_height: int,
        user_agent: str = "Montana/0.1.0",
    ) -> bool:
        """Send Hello message to start handshake."""
        hello = create_hello(services, start_height, user_agent)
        hello.nonce = self.local_nonce

        return await self.send_message(
            MessageType.HELLO,
            hello.serialize()
        )

    async def send_hello_ack(self) -> bool:
        """Send HelloAck to complete handshake."""
        ack = HelloAck(nonce=self.remote_nonce)
        return await self.send_message(
            MessageType.HELLO_ACK,
            ack.serialize()
        )

    async def send_ping(self) -> bool:
        """Send Ping message."""
        nonce = secrets.randbelow(2**64)
        self.pending_ping_nonce = nonce
        self.last_ping = time.time()

        ping = PingMessage(nonce=nonce)
        return await self.send_message(
            MessageType.PING,
            ping.serialize()
        )

    async def send_pong(self, nonce: int) -> bool:
        """Send Pong response."""
        pong = PongMessage(nonce=nonce)
        return await self.send_message(
            MessageType.PONG,
            pong.serialize()
        )

    def handle_pong(self, nonce: int) -> bool:
        """
        Handle Pong response.

        Returns:
            True if valid response to pending ping
        """
        if self.pending_ping_nonce is not None and nonce == self.pending_ping_nonce:
            latency = (time.time() - self.last_ping) * 1000
            self.info.latency_ms = latency
            self.pending_ping_nonce = None
            return True
        return False


class PeerManager:
    """
    Manages peer connections.

    Handles:
    - Peer discovery and connection
    - Connection limits (inbound/outbound)
    - Peer scoring and banning
    """

    def __init__(
        self,
        local_services: int = ServiceFlags.NODE_NETWORK,
        max_peers: int = MAX_PEERS,
        max_inbound: int = MAX_INBOUND_PEERS,
        max_outbound: int = MAX_OUTBOUND_PEERS,
    ):
        self.local_services = local_services
        self.max_peers = max_peers
        self.max_inbound = max_inbound
        self.max_outbound = max_outbound

        # Connected peers
        self.peers: Dict[Tuple[str, int], Peer] = {}

        # Known addresses
        self.known_addresses: Dict[Tuple[str, int], float] = {}  # address -> last_seen

        # Banned addresses
        self.banned: Dict[str, float] = {}  # ip -> ban_until

        # Connection nonces (for self-connection detection)
        self.local_nonces: Set[int] = set()

        # Event handlers
        self._on_peer_connected: List[Callable[[Peer], Any]] = []
        self._on_peer_disconnected: List[Callable[[Peer, DisconnectReason], Any]] = []
        self._on_peer_ready: List[Callable[[Peer], Any]] = []

    @property
    def peer_count(self) -> int:
        return len(self.peers)

    @property
    def inbound_count(self) -> int:
        return sum(1 for p in self.peers.values() if p.is_inbound)

    @property
    def outbound_count(self) -> int:
        return sum(1 for p in self.peers.values() if not p.is_inbound)

    @property
    def ready_peers(self) -> List[Peer]:
        return [p for p in self.peers.values() if p.is_ready]

    def is_banned(self, ip: str) -> bool:
        """Check if IP is banned."""
        if ip in self.banned:
            if time.time() < self.banned[ip]:
                return True
            del self.banned[ip]
        return False

    def ban(self, ip: str, duration_sec: float = 86400):
        """Ban IP for duration."""
        self.banned[ip] = time.time() + duration_sec

    def can_connect_outbound(self) -> bool:
        """Check if we can make new outbound connections."""
        return (
            self.peer_count < self.max_peers and
            self.outbound_count < self.max_outbound
        )

    def can_accept_inbound(self) -> bool:
        """Check if we can accept new inbound connections."""
        return (
            self.peer_count < self.max_peers and
            self.inbound_count < self.max_inbound
        )

    async def connect_peer(self, address: Tuple[str, int]) -> Optional[Peer]:
        """
        Connect to a peer.

        Args:
            address: (ip, port) tuple

        Returns:
            Peer if connected, None on failure
        """
        # Check if already connected
        if address in self.peers:
            return self.peers[address]

        # Check limits
        if not self.can_connect_outbound():
            return None

        # Check ban
        if self.is_banned(address[0]):
            return None

        # Create and connect
        peer = Peer(address=address, is_inbound=False)
        self.local_nonces.add(peer.local_nonce)

        if await peer.connect():
            self.peers[address] = peer
            for handler in self._on_peer_connected:
                await handler(peer) if asyncio.iscoroutinefunction(handler) else handler(peer)
            return peer

        self.local_nonces.discard(peer.local_nonce)
        return None

    async def accept_peer(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Optional[Peer]:
        """
        Accept an inbound connection.

        Args:
            reader: Stream reader
            writer: Stream writer

        Returns:
            Peer if accepted, None on rejection
        """
        peername = writer.get_extra_info('peername')
        if not peername:
            writer.close()
            return None

        address = (peername[0], peername[1])

        # Check if already connected
        if address in self.peers:
            writer.close()
            return None

        # Check limits
        if not self.can_accept_inbound():
            writer.close()
            return None

        # Check ban
        if self.is_banned(address[0]):
            writer.close()
            return None

        # Create peer
        peer = Peer(
            address=address,
            is_inbound=True,
            reader=reader,
            writer=writer,
            state=PeerState.CONNECTED,
        )
        peer.connect_time = time.time()
        self.local_nonces.add(peer.local_nonce)

        self.peers[address] = peer
        for handler in self._on_peer_connected:
            await handler(peer) if asyncio.iscoroutinefunction(handler) else handler(peer)

        return peer

    async def disconnect_peer(
        self,
        address: Tuple[str, int],
        reason: DisconnectReason = DisconnectReason.REQUESTED,
    ):
        """Disconnect from a peer."""
        if address not in self.peers:
            return

        peer = self.peers[address]
        self.local_nonces.discard(peer.local_nonce)

        await peer.disconnect(reason)
        del self.peers[address]

        for handler in self._on_peer_disconnected:
            await handler(peer, reason) if asyncio.iscoroutinefunction(handler) else handler(peer, reason)

    def is_self_connection(self, nonce: int) -> bool:
        """Check if nonce indicates self-connection."""
        return nonce in self.local_nonces

    def add_known_address(self, address: Tuple[str, int], last_seen: float = 0.0):
        """Add address to known addresses."""
        self.known_addresses[address] = last_seen or time.time()

    def get_addresses_for_peer(self, count: int = 1000) -> List[Tuple[str, int, float]]:
        """Get addresses to share with peer."""
        # Sort by last seen, most recent first
        sorted_addrs = sorted(
            self.known_addresses.items(),
            key=lambda x: x[1],
            reverse=True
        )[:count]

        return [(addr[0], addr[1], ts) for addr, ts in sorted_addrs]

    def on_peer_connected(self, handler: Callable[[Peer], Any]):
        """Register handler for peer connected event."""
        self._on_peer_connected.append(handler)

    def on_peer_disconnected(self, handler: Callable[[Peer, DisconnectReason], Any]):
        """Register handler for peer disconnected event."""
        self._on_peer_disconnected.append(handler)

    def on_peer_ready(self, handler: Callable[[Peer], Any]):
        """Register handler for peer ready event."""
        self._on_peer_ready.append(handler)

    async def mark_peer_ready(self, peer: Peer):
        """Mark peer as ready after handshake."""
        peer.state = PeerState.READY
        peer.handshake_complete = True

        for handler in self._on_peer_ready:
            await handler(peer) if asyncio.iscoroutinefunction(handler) else handler(peer)
