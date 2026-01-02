"""
Ɉ Montana Atomic Time Layer v3.1

Layer 0: Global Atomic Time per MONTANA_TECHNICAL_SPECIFICATION.md §4.

Implements Byzantine median consensus over 34 NTP sources across 8 regions.
Requires >50% (18+) agreeing sources for valid time consensus.
"""

from __future__ import annotations
import asyncio
import socket
import struct
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum

from montana.constants import (
    NTP_SOURCES,
    NTP_TOTAL_SOURCES,
    NTP_MIN_SOURCES_CONSENSUS,
    NTP_MIN_SOURCES_CONTINENT,
    NTP_MIN_REGIONS_TOTAL,
    NTP_QUERY_TIMEOUT_MS,
    NTP_MAX_DRIFT_MS,
    NTP_MAX_RETRY,
    NTP_QUERY_INTERVAL_SEC,
)

logger = logging.getLogger(__name__)


class TimeConsensusStatus(IntEnum):
    """Status of atomic time consensus."""
    VALID = 0          # Consensus achieved
    INSUFFICIENT = 1   # Not enough sources responded
    DIVERGENT = 2      # Sources disagree beyond tolerance
    ERROR = 3          # Query failed


@dataclass
class NTPResponse:
    """Response from a single NTP query."""
    source_name: str
    server: str
    region: str
    offset_ms: float      # Local time offset in milliseconds
    rtt_ms: float         # Round-trip time in milliseconds
    stratum: int          # NTP stratum level
    timestamp_utc: float  # Server timestamp (UNIX epoch)
    success: bool
    error: Optional[str] = None


@dataclass
class TimeConsensus:
    """Result of Byzantine time consensus."""
    status: TimeConsensusStatus
    consensus_time_utc: float        # Consensus timestamp (UNIX epoch)
    local_offset_ms: float           # Offset to apply to local clock
    responding_sources: int          # Number of sources that responded
    agreeing_sources: int            # Number of sources within tolerance
    regions_covered: int             # Number of distinct regions
    responses: List[NTPResponse] = field(default_factory=list)
    error: Optional[str] = None


class NTPClient:
    """
    Async NTP client for querying time servers.

    Implements NTP v4 protocol for obtaining timestamps.
    """

    NTP_DELTA = 2208988800  # Seconds between 1900 and 1970
    NTP_PORT = 123

    def __init__(self, timeout_ms: int = NTP_QUERY_TIMEOUT_MS):
        self.timeout_sec = timeout_ms / 1000.0

    async def query(self, server: str, source_name: str, region: str) -> NTPResponse:
        """
        Query a single NTP server.

        Args:
            server: NTP server hostname
            source_name: Human-readable source name (e.g., "NIST")
            region: Geographic region

        Returns:
            NTPResponse with timing data
        """
        try:
            return await asyncio.wait_for(
                self._query_impl(server, source_name, region),
                timeout=self.timeout_sec
            )
        except asyncio.TimeoutError:
            return NTPResponse(
                source_name=source_name,
                server=server,
                region=region,
                offset_ms=0.0,
                rtt_ms=0.0,
                stratum=16,
                timestamp_utc=0.0,
                success=False,
                error="Timeout"
            )
        except Exception as e:
            return NTPResponse(
                source_name=source_name,
                server=server,
                region=region,
                offset_ms=0.0,
                rtt_ms=0.0,
                stratum=16,
                timestamp_utc=0.0,
                success=False,
                error=str(e)
            )

    async def _query_impl(self, server: str, source_name: str, region: str) -> NTPResponse:
        """Internal NTP query implementation."""
        # Create NTP request packet (mode 3 = client, version 4)
        # LI=0, VN=4, Mode=3 => 0b00_100_011 = 0x23
        request = bytearray(48)
        request[0] = 0x23

        loop = asyncio.get_event_loop()

        # Record send time
        t1 = time.time()

        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        try:
            # Resolve hostname and send request
            addr = await loop.getaddrinfo(server, self.NTP_PORT, family=socket.AF_INET)
            if not addr:
                raise Exception(f"Cannot resolve {server}")

            target = addr[0][4]
            await loop.sock_sendto(sock, request, target)

            # Receive response
            response, _ = await loop.sock_recvfrom(sock, 48)
            t4 = time.time()

            if len(response) < 48:
                raise Exception("Invalid NTP response length")

            # Parse response
            stratum = response[1]

            # Extract timestamps (transmit time at offset 40)
            tx_time_int = struct.unpack('!I', response[40:44])[0]
            tx_time_frac = struct.unpack('!I', response[44:48])[0]
            tx_time = tx_time_int - self.NTP_DELTA + tx_time_frac / (2**32)

            # Calculate offset and RTT
            # Simplified: offset = server_time - local_time
            rtt = t4 - t1
            offset = tx_time - t4 + (rtt / 2)

            return NTPResponse(
                source_name=source_name,
                server=server,
                region=region,
                offset_ms=offset * 1000,
                rtt_ms=rtt * 1000,
                stratum=stratum,
                timestamp_utc=tx_time,
                success=True
            )

        finally:
            sock.close()


class AtomicTimeSynchronizer:
    """
    Byzantine fault-tolerant time synchronization per §4.

    Queries 34 NTP sources across 8 regions and computes Byzantine
    median to achieve consensus time within 1000ms tolerance.
    """

    def __init__(
        self,
        sources: Optional[Dict[str, List[Tuple[str, str, str]]]] = None,
        max_drift_ms: int = NTP_MAX_DRIFT_MS,
        min_sources: int = NTP_MIN_SOURCES_CONSENSUS,
        min_regions: int = NTP_MIN_REGIONS_TOTAL,
    ):
        """
        Initialize the time synchronizer.

        Args:
            sources: NTP sources by region (defaults to NTP_SOURCES)
            max_drift_ms: Maximum acceptable drift between sources
            min_sources: Minimum agreeing sources for consensus
            min_regions: Minimum distinct regions required
        """
        self.sources = sources or NTP_SOURCES
        self.max_drift_ms = max_drift_ms
        self.min_sources = min_sources
        self.min_regions = min_regions
        self.ntp_client = NTPClient()

        # Cache last consensus
        self._last_consensus: Optional[TimeConsensus] = None
        self._last_sync_time: float = 0.0

    async def synchronize(self) -> TimeConsensus:
        """
        Query all NTP sources and compute Byzantine median consensus.

        Returns:
            TimeConsensus with status and consensus time
        """
        # Collect all sources into flat list
        all_sources: List[Tuple[str, str, str]] = []
        for region, sources in self.sources.items():
            for name, server, country in sources:
                all_sources.append((name, server, region))

        # Query all sources concurrently
        tasks = [
            self.ntp_client.query(server, name, region)
            for name, server, region in all_sources
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful responses
        valid_responses: List[NTPResponse] = []
        for r in responses:
            if isinstance(r, NTPResponse) and r.success:
                valid_responses.append(r)

        logger.debug(f"NTP: {len(valid_responses)}/{len(all_sources)} sources responded")

        # Check minimum sources
        if len(valid_responses) < self.min_sources:
            return TimeConsensus(
                status=TimeConsensusStatus.INSUFFICIENT,
                consensus_time_utc=time.time(),
                local_offset_ms=0.0,
                responding_sources=len(valid_responses),
                agreeing_sources=0,
                regions_covered=0,
                responses=valid_responses,
                error=f"Only {len(valid_responses)} sources responded, need {self.min_sources}"
            )

        # Compute Byzantine median
        return self._compute_byzantine_median(valid_responses)

    def _compute_byzantine_median(self, responses: List[NTPResponse]) -> TimeConsensus:
        """
        Compute Byzantine fault-tolerant median of time offsets.

        Uses the Marzullo algorithm variant:
        1. Sort offsets
        2. Find the largest cluster within tolerance
        3. Use cluster median as consensus
        """
        # Sort by offset
        sorted_responses = sorted(responses, key=lambda r: r.offset_ms)
        offsets = [r.offset_ms for r in sorted_responses]

        # Find largest cluster within tolerance
        best_cluster: List[int] = []
        best_start = 0

        for i in range(len(offsets)):
            # Find all responses within tolerance of response[i]
            cluster = []
            for j in range(len(offsets)):
                if abs(offsets[j] - offsets[i]) <= self.max_drift_ms:
                    cluster.append(j)

            if len(cluster) > len(best_cluster):
                best_cluster = cluster
                best_start = i

        # Check if cluster is large enough
        if len(best_cluster) < self.min_sources:
            return TimeConsensus(
                status=TimeConsensusStatus.DIVERGENT,
                consensus_time_utc=time.time(),
                local_offset_ms=0.0,
                responding_sources=len(responses),
                agreeing_sources=len(best_cluster),
                regions_covered=0,
                responses=responses,
                error=f"Only {len(best_cluster)} sources agree, need {self.min_sources}"
            )

        # Count regions in cluster
        cluster_responses = [sorted_responses[i] for i in best_cluster]
        regions = set(r.region for r in cluster_responses)

        if len(regions) < self.min_regions:
            return TimeConsensus(
                status=TimeConsensusStatus.DIVERGENT,
                consensus_time_utc=time.time(),
                local_offset_ms=0.0,
                responding_sources=len(responses),
                agreeing_sources=len(best_cluster),
                regions_covered=len(regions),
                responses=responses,
                error=f"Only {len(regions)} regions covered, need {self.min_regions}"
            )

        # Compute median offset of cluster
        cluster_offsets = sorted([offsets[i] for i in best_cluster])
        median_idx = len(cluster_offsets) // 2
        median_offset = cluster_offsets[median_idx]

        # Compute consensus time
        consensus_time = time.time() + (median_offset / 1000.0)

        # Cache result
        self._last_consensus = TimeConsensus(
            status=TimeConsensusStatus.VALID,
            consensus_time_utc=consensus_time,
            local_offset_ms=median_offset,
            responding_sources=len(responses),
            agreeing_sources=len(best_cluster),
            regions_covered=len(regions),
            responses=responses
        )
        self._last_sync_time = time.time()

        logger.info(
            f"Time consensus: {len(best_cluster)}/{len(responses)} sources, "
            f"{len(regions)} regions, offset={median_offset:.1f}ms"
        )

        return self._last_consensus

    def get_current_time(self) -> float:
        """
        Get current consensus-adjusted time.

        Returns:
            UNIX timestamp adjusted by last known offset
        """
        if self._last_consensus and self._last_consensus.status == TimeConsensusStatus.VALID:
            return time.time() + (self._last_consensus.local_offset_ms / 1000.0)
        return time.time()

    def get_current_time_ms(self) -> int:
        """Get current consensus-adjusted time in milliseconds."""
        return int(self.get_current_time() * 1000)

    @property
    def is_synchronized(self) -> bool:
        """Check if we have valid time consensus."""
        if not self._last_consensus:
            return False
        return self._last_consensus.status == TimeConsensusStatus.VALID

    @property
    def last_consensus(self) -> Optional[TimeConsensus]:
        """Get last time consensus result."""
        return self._last_consensus


# Global synchronizer instance
_synchronizer: Optional[AtomicTimeSynchronizer] = None


def get_synchronizer() -> AtomicTimeSynchronizer:
    """Get or create the global time synchronizer."""
    global _synchronizer
    if _synchronizer is None:
        _synchronizer = AtomicTimeSynchronizer()
    return _synchronizer


async def synchronize_time() -> TimeConsensus:
    """Synchronize time using global synchronizer."""
    return await get_synchronizer().synchronize()


def get_atomic_time() -> float:
    """Get current atomic time (consensus-adjusted)."""
    return get_synchronizer().get_current_time()


def get_atomic_time_ms() -> int:
    """Get current atomic time in milliseconds."""
    return get_synchronizer().get_current_time_ms()
