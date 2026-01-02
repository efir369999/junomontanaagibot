"""
Ɉ Montana Handshake Protocol v3.1

Hello/HelloAck handshake per MONTANA_TECHNICAL_SPECIFICATION.md §17.5.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from montana.constants import (
    PROTOCOL_VERSION,
    PEER_HANDSHAKE_TIMEOUT_SEC,
)
from montana.network.protocol import MessageType, ServiceFlags
from montana.network.messages import HelloMessage, HelloAck, create_hello
from montana.network.peer import Peer, PeerState, PeerManager, DisconnectReason

logger = logging.getLogger(__name__)


@dataclass
class HandshakeResult:
    """Result of handshake attempt."""
    success: bool
    error: Optional[str] = None
    version: int = 0
    services: int = 0
    start_height: int = 0
    user_agent: str = ""


class HandshakeProtocol:
    """
    Implements the Hello/HelloAck handshake protocol.

    Handshake flow:
    1. Initiator sends Hello
    2. Responder sends Hello + HelloAck
    3. Initiator sends HelloAck
    4. Both sides are now ready

    Per §17.5.1-17.5.2.
    """

    def __init__(
        self,
        peer_manager: PeerManager,
        local_services: int = ServiceFlags.NODE_NETWORK,
        start_height: int = 0,
        user_agent: str = "Montana/0.1.0",
    ):
        self.peer_manager = peer_manager
        self.local_services = local_services
        self.start_height = start_height
        self.user_agent = user_agent

    async def perform_outbound_handshake(
        self,
        peer: Peer,
        timeout: float = PEER_HANDSHAKE_TIMEOUT_SEC,
    ) -> HandshakeResult:
        """
        Perform handshake as initiating (outbound) peer.

        Flow:
        1. Send Hello
        2. Receive Hello
        3. Receive HelloAck (verifies our nonce)
        4. Send HelloAck (echo their nonce)

        Args:
            peer: Connected peer
            timeout: Handshake timeout

        Returns:
            HandshakeResult with success/failure info
        """
        peer.state = PeerState.HANDSHAKING

        try:
            # Step 1: Send Hello
            if not await peer.send_hello(
                self.local_services,
                self.start_height,
                self.user_agent,
            ):
                return HandshakeResult(False, "Failed to send Hello")

            # Step 2: Receive Hello
            result = await peer.receive_message(timeout)
            if not result:
                return HandshakeResult(False, "Timeout waiting for Hello")

            msg_type, payload = result
            if msg_type != MessageType.HELLO:
                return HandshakeResult(False, f"Expected Hello, got {msg_type.name}")

            hello = HelloMessage.deserialize(payload)

            # Check for self-connection
            if self.peer_manager.is_self_connection(hello.nonce):
                await peer.disconnect(DisconnectReason.SELF_CONNECTION)
                return HandshakeResult(False, "Self-connection detected")

            # Check version compatibility
            if hello.version < 1:
                await peer.disconnect(DisconnectReason.INCOMPATIBLE_VERSION)
                return HandshakeResult(False, f"Incompatible version: {hello.version}")

            peer.remote_nonce = hello.nonce
            peer.info.version = hello.version
            peer.info.services = hello.services
            peer.info.user_agent = hello.user_agent
            peer.info.start_height = hello.start_height

            # Step 3: Receive HelloAck
            result = await peer.receive_message(timeout)
            if not result:
                return HandshakeResult(False, "Timeout waiting for HelloAck")

            msg_type, payload = result
            if msg_type != MessageType.HELLO_ACK:
                return HandshakeResult(False, f"Expected HelloAck, got {msg_type.name}")

            ack = HelloAck.deserialize(payload)

            # Verify they echoed our nonce
            if ack.nonce != peer.local_nonce:
                return HandshakeResult(False, "HelloAck nonce mismatch")

            # Step 4: Send HelloAck
            if not await peer.send_hello_ack():
                return HandshakeResult(False, "Failed to send HelloAck")

            # Handshake complete
            await self.peer_manager.mark_peer_ready(peer)

            logger.info(
                f"Handshake complete with {peer.address[0]}:{peer.address[1]} "
                f"v{hello.version} {hello.user_agent} height={hello.start_height}"
            )

            return HandshakeResult(
                success=True,
                version=hello.version,
                services=hello.services,
                start_height=hello.start_height,
                user_agent=hello.user_agent,
            )

        except Exception as e:
            logger.error(f"Handshake error: {e}")
            return HandshakeResult(False, str(e))

    async def perform_inbound_handshake(
        self,
        peer: Peer,
        timeout: float = PEER_HANDSHAKE_TIMEOUT_SEC,
    ) -> HandshakeResult:
        """
        Perform handshake as responding (inbound) peer.

        Flow:
        1. Receive Hello
        2. Send Hello + HelloAck
        3. Receive HelloAck

        Args:
            peer: Connected peer
            timeout: Handshake timeout

        Returns:
            HandshakeResult with success/failure info
        """
        peer.state = PeerState.HANDSHAKING

        try:
            # Step 1: Receive Hello
            result = await peer.receive_message(timeout)
            if not result:
                return HandshakeResult(False, "Timeout waiting for Hello")

            msg_type, payload = result
            if msg_type != MessageType.HELLO:
                return HandshakeResult(False, f"Expected Hello, got {msg_type.name}")

            hello = HelloMessage.deserialize(payload)

            # Check for self-connection
            if self.peer_manager.is_self_connection(hello.nonce):
                await peer.disconnect(DisconnectReason.SELF_CONNECTION)
                return HandshakeResult(False, "Self-connection detected")

            # Check version compatibility
            if hello.version < 1:
                await peer.disconnect(DisconnectReason.INCOMPATIBLE_VERSION)
                return HandshakeResult(False, f"Incompatible version: {hello.version}")

            peer.remote_nonce = hello.nonce
            peer.info.version = hello.version
            peer.info.services = hello.services
            peer.info.user_agent = hello.user_agent
            peer.info.start_height = hello.start_height

            # Step 2: Send Hello
            if not await peer.send_hello(
                self.local_services,
                self.start_height,
                self.user_agent,
            ):
                return HandshakeResult(False, "Failed to send Hello")

            # Step 2b: Send HelloAck (echo their nonce)
            if not await peer.send_hello_ack():
                return HandshakeResult(False, "Failed to send HelloAck")

            # Step 3: Receive HelloAck
            result = await peer.receive_message(timeout)
            if not result:
                return HandshakeResult(False, "Timeout waiting for HelloAck")

            msg_type, payload = result
            if msg_type != MessageType.HELLO_ACK:
                return HandshakeResult(False, f"Expected HelloAck, got {msg_type.name}")

            ack = HelloAck.deserialize(payload)

            # Verify they echoed our nonce
            if ack.nonce != peer.local_nonce:
                return HandshakeResult(False, "HelloAck nonce mismatch")

            # Handshake complete
            await self.peer_manager.mark_peer_ready(peer)

            logger.info(
                f"Handshake complete with {peer.address[0]}:{peer.address[1]} "
                f"v{hello.version} {hello.user_agent} height={hello.start_height}"
            )

            return HandshakeResult(
                success=True,
                version=hello.version,
                services=hello.services,
                start_height=hello.start_height,
                user_agent=hello.user_agent,
            )

        except Exception as e:
            logger.error(f"Handshake error: {e}")
            return HandshakeResult(False, str(e))


async def perform_handshake(
    peer: Peer,
    peer_manager: PeerManager,
    local_services: int,
    start_height: int,
    user_agent: str = "Montana/0.1.0",
    timeout: float = PEER_HANDSHAKE_TIMEOUT_SEC,
) -> HandshakeResult:
    """
    Convenience function to perform handshake.

    Automatically selects outbound or inbound handshake based on peer type.
    """
    protocol = HandshakeProtocol(
        peer_manager,
        local_services,
        start_height,
        user_agent,
    )

    if peer.is_inbound:
        return await protocol.perform_inbound_handshake(peer, timeout)
    else:
        return await protocol.perform_outbound_handshake(peer, timeout)
