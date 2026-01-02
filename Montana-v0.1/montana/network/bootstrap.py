"""
Ɉ Montana Bootstrap Nodes v3.1

Bootstrap node discovery per MONTANA_TECHNICAL_SPECIFICATION.md §17.4.
"""

from __future__ import annotations
import asyncio
import logging
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from montana.constants import (
    DEFAULT_PORT,
    BOOTSTRAP_NODES,
)
from montana.network.protocol import ServiceFlags
from montana.network.peer import Peer, PeerManager

logger = logging.getLogger(__name__)


@dataclass
class BootstrapNode:
    """Bootstrap node information."""
    name: str
    ip: str
    port: int = DEFAULT_PORT
    region: str = "unknown"
    services: int = ServiceFlags.NODE_NETWORK | ServiceFlags.NODE_VDF

    @property
    def address(self) -> Tuple[str, int]:
        return (self.ip, self.port)


# Official bootstrap nodes per §17.4.1
OFFICIAL_BOOTSTRAP_NODES: List[BootstrapNode] = [
    BootstrapNode(
        name="montana-genesis-1",
        ip="176.124.208.93",
        port=DEFAULT_PORT,
        region="EU",
        services=ServiceFlags.NODE_NETWORK | ServiceFlags.NODE_VDF | ServiceFlags.NODE_NTP,
    ),
]

# DNS seeds for future expansion
DNS_SEEDS: List[str] = [
    # "seed.montana.network",  # Future
]


class BootstrapManager:
    """
    Manages bootstrap node connections.

    Bootstrap nodes are used for:
    - Initial peer discovery
    - Network entry after cold start
    - Fallback when no peers available
    """

    def __init__(
        self,
        peer_manager: PeerManager,
        bootstrap_nodes: Optional[List[BootstrapNode]] = None,
    ):
        self.peer_manager = peer_manager
        self.bootstrap_nodes = bootstrap_nodes or OFFICIAL_BOOTSTRAP_NODES.copy()
        self._connected_bootstrap: List[Peer] = []

    @property
    def bootstrap_addresses(self) -> List[Tuple[str, int]]:
        """Get all bootstrap addresses."""
        return [node.address for node in self.bootstrap_nodes]

    def add_bootstrap_node(self, node: BootstrapNode):
        """Add a bootstrap node."""
        if node.address not in self.bootstrap_addresses:
            self.bootstrap_nodes.append(node)

    async def connect_to_bootstrap(
        self,
        min_connections: int = 1,
        timeout: float = 30.0,
    ) -> int:
        """
        Connect to bootstrap nodes.

        Args:
            min_connections: Minimum number of bootstrap connections
            timeout: Connection timeout

        Returns:
            Number of successful connections
        """
        if not self.bootstrap_nodes:
            logger.warning("No bootstrap nodes configured")
            return 0

        # Shuffle to distribute load
        nodes = self.bootstrap_nodes.copy()
        random.shuffle(nodes)

        connected = 0
        for node in nodes:
            if connected >= min_connections:
                break

            if self.peer_manager.is_banned(node.ip):
                logger.debug(f"Skipping banned bootstrap: {node.name}")
                continue

            logger.info(f"Connecting to bootstrap: {node.name} ({node.ip}:{node.port})")

            peer = await self.peer_manager.connect_peer(node.address)
            if peer:
                self._connected_bootstrap.append(peer)
                connected += 1
                logger.info(f"Connected to bootstrap: {node.name}")
            else:
                logger.warning(f"Failed to connect to bootstrap: {node.name}")

        return connected

    async def resolve_dns_seeds(self) -> List[Tuple[str, int]]:
        """
        Resolve DNS seeds to addresses.

        Returns:
            List of resolved addresses
        """
        addresses = []

        for seed in DNS_SEEDS:
            try:
                # Resolve DNS
                loop = asyncio.get_event_loop()
                result = await loop.getaddrinfo(
                    seed, DEFAULT_PORT,
                    family=0,
                    type=1,  # SOCK_STREAM
                )

                for info in result:
                    ip = info[4][0]
                    addresses.append((ip, DEFAULT_PORT))
                    logger.debug(f"Resolved {seed} -> {ip}")

            except Exception as e:
                logger.warning(f"Failed to resolve DNS seed {seed}: {e}")

        return addresses

    async def bootstrap_network(
        self,
        min_peers: int = 8,
        timeout: float = 60.0,
    ) -> bool:
        """
        Bootstrap the network connection.

        Tries:
        1. Connect to hardcoded bootstrap nodes
        2. Resolve DNS seeds
        3. Request addresses from connected peers

        Args:
            min_peers: Minimum number of peers to connect to
            timeout: Overall bootstrap timeout

        Returns:
            True if minimum peers reached
        """
        start_time = asyncio.get_event_loop().time()

        # Step 1: Connect to bootstrap nodes
        logger.info("Bootstrapping network...")
        bootstrap_count = await self.connect_to_bootstrap(min_connections=2)

        if bootstrap_count == 0:
            logger.error("Failed to connect to any bootstrap nodes")
            # Try DNS seeds as fallback
            addresses = await self.resolve_dns_seeds()
            for addr in addresses[:3]:
                await self.peer_manager.connect_peer(addr)

        # Step 2: Request addresses from connected peers
        # (This would trigger GetAddr/Addr message exchange)
        # Implementation depends on message handler setup

        # Step 3: Wait for minimum peers
        while asyncio.get_event_loop().time() - start_time < timeout:
            if len(self.peer_manager.ready_peers) >= min_peers:
                logger.info(f"Bootstrap complete: {len(self.peer_manager.ready_peers)} peers")
                return True

            await asyncio.sleep(1.0)

        peer_count = len(self.peer_manager.ready_peers)
        if peer_count > 0:
            logger.warning(f"Bootstrap timeout with {peer_count} peers (target: {min_peers})")
            return True  # Some peers is better than none
        else:
            logger.error("Bootstrap failed: no peers connected")
            return False


def get_bootstrap_addresses() -> List[Tuple[str, int]]:
    """Get list of bootstrap node addresses."""
    return [node.address for node in OFFICIAL_BOOTSTRAP_NODES]


def parse_bootstrap_string(bootstrap_str: str) -> Optional[BootstrapNode]:
    """
    Parse bootstrap string like "ip:port" or "name@ip:port".

    Args:
        bootstrap_str: Bootstrap specification

    Returns:
        BootstrapNode or None on parse error
    """
    try:
        # Check for name@address format
        if "@" in bootstrap_str:
            name, address = bootstrap_str.split("@", 1)
        else:
            name = "custom"
            address = bootstrap_str

        # Parse address
        if ":" in address:
            ip, port_str = address.rsplit(":", 1)
            port = int(port_str)
        else:
            ip = address
            port = DEFAULT_PORT

        return BootstrapNode(name=name, ip=ip, port=port)

    except Exception as e:
        logger.error(f"Failed to parse bootstrap string '{bootstrap_str}': {e}")
        return None
