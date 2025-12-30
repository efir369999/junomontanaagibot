"""
Montana v4.0 - Adam Sync: THE CANONICAL TIME SYNCHRONIZATION MODULE

ADAM = Anchored Deterministic Asynchronous Mesh

THIS IS THE ONLY SOURCE OF TRUTH FOR TIME SYNCHRONIZATION IN MONTANA.
All other time-related modules MUST use Adam Sync. No exceptions.

═══════════════════════════════════════════════════════════════════════════════
                           ADAM SYNC LEVELS (0-6)
═══════════════════════════════════════════════════════════════════════════════

  LEVEL 0: NTP_SERVERS
  ────────────────────
  External NTP/Roughtime servers for reference.
  Weighted average from multiple sources.
  Trust: LOW (can be spoofed, network dependent)

           ▼

  LEVEL 1: NODE_UTC
  ─────────────────
  Node's hardware clock synchronized to UTC.
  Calibrated against Level 0.
  Trust: MEDIUM (local hardware, drift possible)

           ▼

  LEVEL 2: MEMPOOL_TIME
  ─────────────────────
  Transaction enters Bitcoin mempool.
  Timestamp when TX is first seen by network.
  Trust: MEDIUM-HIGH (distributed observation)
  State: PENDING

           ▼

  LEVEL 3: BLOCK_TIME
  ───────────────────
  Transaction included in Bitcoin block.
  Block timestamp from miner.
  Trust: HIGH (PoW secured)
  State: TENTATIVE → CONFIRMED → IRREVERSIBLE

           ▼

  LEVEL 4: BITCOIN_ACTIVE
  ───────────────────────
  Bitcoin is producing blocks normally.
  VDF fallback is IDLE (not needed).
  This is the normal operating state.

           ▼ (only if Bitcoin fails)

  LEVEL 5: VDF_FALLBACK
  ─────────────────────
  Bitcoin unavailable for 2+ blocks (~20 min).
  VDF provides sovereign timekeeping.
  Trust: HIGH (cryptographic, sequential)

           ▼ (when Bitcoin returns)

  LEVEL 6: VDF_DEACTIVATE
  ───────────────────────
  Bitcoin resumed producing blocks.
  VDF fallback deactivates.
  Return to LEVEL 4.

═══════════════════════════════════════════════════════════════════════════════

FINALITY PROGRESSION (Level 3):
───────────────────────────────
  PENDING      (0 conf)   - In mempool, not in block
  TENTATIVE    (1 conf)   - In block, may reorg
  CONFIRMED    (6+ conf)  - Probabilistic finality
  IRREVERSIBLE (100+ conf) - Economic finality, cannot reorg

Bitcoin is the clock. VDF is the insurance.
Time is the ultimate proof.
"""

import time
import struct
import hashlib
import logging
import threading
import statistics
import socket
from typing import Optional, Tuple, Dict, Any, List, Callable, Set
from dataclasses import dataclass, field
from enum import IntEnum, auto
from collections import deque
from abc import ABC, abstractmethod

logger = logging.getLogger("montana.adam_sync")


# ============================================================================
# ADAM SYNC LEVELS
# ============================================================================

class AdamLevel(IntEnum):
    """
    Adam Sync canonical levels.

    This is the ONLY definition of time synchronization levels in Montana.
    """
    NTP_SERVERS = 0       # External NTP servers
    NODE_UTC = 1          # Node hardware clock (UTC)
    MEMPOOL_TIME = 2      # Bitcoin mempool observation
    BLOCK_TIME = 3        # Bitcoin block confirmation
    BITCOIN_ACTIVE = 4    # Bitcoin working, VDF idle
    VDF_FALLBACK = 5      # Bitcoin down, VDF active
    VDF_DEACTIVATE = 6    # Bitcoin back, VDF off


class FinalityState(IntEnum):
    """
    Transaction/block finality states.

    Progressive finality from mempool to irreversible.
    """
    UNKNOWN = 0           # State unknown
    PENDING = 1           # In mempool (Level 2)
    TENTATIVE = 2         # 1 confirmation (Level 3)
    CONFIRMED = 3         # 6+ confirmations (Level 3)
    IRREVERSIBLE = 4      # 100+ confirmations (Level 3)

    @classmethod
    def from_confirmations(cls, confirmations: int) -> 'FinalityState':
        """Convert confirmation count to finality state."""
        if confirmations <= 0:
            return cls.PENDING
        elif confirmations < CONFIRMATIONS_CONFIRMED:
            return cls.TENTATIVE
        elif confirmations < CONFIRMATIONS_IRREVERSIBLE:
            return cls.CONFIRMED
        else:
            return cls.IRREVERSIBLE

    @property
    def can_reorg(self) -> bool:
        """Check if this state can be reorganized."""
        return self != FinalityState.IRREVERSIBLE

    @property
    def is_final(self) -> bool:
        """Check if this state represents finality."""
        return self == FinalityState.IRREVERSIBLE


class LevelState(IntEnum):
    """State of each Adam level."""
    INACTIVE = 0      # Level not initialized
    SYNCING = 1       # Level synchronizing
    ACTIVE = 2        # Level operational
    DEGRADED = 3      # Level experiencing issues
    FAILED = 4        # Level unavailable


# ============================================================================
# CONSTANTS - THE CANONICAL VALUES
# ============================================================================

# Level 0: NTP Servers
NTP_SERVERS = [
    "time.google.com",
    "time.cloudflare.com",
    "time.apple.com",
    "pool.ntp.org",
    "time.windows.com",
]
NTP_TIMEOUT_SEC = 2.0
NTP_MIN_SERVERS = 3
NTP_SYNC_INTERVAL = 60  # seconds

# Level 1: Node UTC
MAX_CLOCK_DRIFT_MS = 500
DRIFT_CORRECTION_INTERVAL = 1  # seconds

# Level 2: Mempool
MEMPOOL_POLL_INTERVAL = 30  # seconds

# Level 3: Block confirmations
CONFIRMATIONS_TENTATIVE = 1
CONFIRMATIONS_CONFIRMED = 6
CONFIRMATIONS_IRREVERSIBLE = 100

# Level 4/5: Bitcoin/VDF
BITCOIN_BLOCK_TIME = 600  # 10 minutes expected
BITCOIN_MAX_VARIANCE = 1800  # 30 minutes max
VDF_TRIGGER_BLOCKS = 2  # 2 missed blocks triggers VDF
VDF_TRIGGER_SECONDS = VDF_TRIGGER_BLOCKS * BITCOIN_BLOCK_TIME  # ~20 min


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Level0Result:
    """Level 0: NTP server query result."""
    server: str
    ntp_time: float           # Time from NTP server
    round_trip_ms: float      # Network round-trip
    offset_ms: float          # Offset from local clock
    confidence: float         # 0.0-1.0 based on round-trip
    queried_at: float         # Local time when queried

    @property
    def adjusted_time(self) -> float:
        """Time adjusted for network latency."""
        return self.ntp_time + (self.round_trip_ms / 2000.0)


@dataclass
class Level1State:
    """Level 1: Node UTC state."""
    utc_time: float           # Current UTC time
    local_time: float         # Local system time
    offset_ms: float          # Offset from NTP consensus
    drift_rate_ms_min: float  # Drift rate in ms/minute
    last_sync: float          # Last NTP sync time
    synced: bool              # Is clock synced?


@dataclass
class Level2State:
    """Level 2: Mempool state."""
    tx_count: int             # Pending transactions
    size_bytes: int           # Total mempool size
    fee_min: float            # Min fee rate (sat/vB)
    fee_median: float         # Median fee rate
    fee_high: float           # High priority fee rate
    first_seen: Dict[bytes, float] = field(default_factory=dict)  # TX hash -> first seen time
    last_update: float = 0.0


@dataclass
class Level3Block:
    """Level 3: Bitcoin block."""
    height: int
    hash: bytes               # 32 bytes
    prev_hash: bytes          # 32 bytes
    timestamp: int            # Block timestamp (miner)
    merkle_root: bytes        # 32 bytes
    confirmations: int = 0
    finality: FinalityState = FinalityState.TENTATIVE
    received_at: float = 0.0  # When node received it

    def update_finality(self, chain_height: int):
        """Update finality based on current chain height."""
        self.confirmations = max(0, chain_height - self.height + 1)
        self.finality = FinalityState.from_confirmations(self.confirmations)

    @property
    def hash_hex(self) -> str:
        """Block hash as hex (display format)."""
        return self.hash[::-1].hex()

    def serialize(self) -> bytes:
        """Serialize block."""
        data = bytearray()
        data.extend(struct.pack('<Q', self.height))
        data.extend(self.hash)
        data.extend(self.prev_hash)
        data.extend(struct.pack('<Q', self.timestamp))
        data.extend(self.merkle_root)
        data.extend(struct.pack('<I', self.confirmations))
        data.extend(struct.pack('<B', self.finality))
        data.extend(struct.pack('<d', self.received_at))
        return bytes(data)

    @classmethod
    def deserialize(cls, data: bytes, offset: int = 0) -> Tuple['Level3Block', int]:
        """Deserialize block."""
        height = struct.unpack_from('<Q', data, offset)[0]
        offset += 8
        block_hash = data[offset:offset + 32]
        offset += 32
        prev_hash = data[offset:offset + 32]
        offset += 32
        timestamp = struct.unpack_from('<Q', data, offset)[0]
        offset += 8
        merkle_root = data[offset:offset + 32]
        offset += 32
        confirmations = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        finality = FinalityState(struct.unpack_from('<B', data, offset)[0])
        offset += 1
        received_at = struct.unpack_from('<d', data, offset)[0]
        offset += 8

        return cls(
            height=height,
            hash=block_hash,
            prev_hash=prev_hash,
            timestamp=timestamp,
            merkle_root=merkle_root,
            confirmations=confirmations,
            finality=finality,
            received_at=received_at
        ), offset


@dataclass
class AdamTimestamp:
    """
    THE canonical timestamp from Adam Sync.

    Contains state from all levels.
    """
    # Level 0: NTP
    ntp_servers_responding: int
    ntp_consensus_offset_ms: float

    # Level 1: Node UTC
    utc_time: float
    local_time: float
    clock_drift_ms: float

    # Level 2: Mempool (if TX pending)
    mempool_first_seen: Optional[float] = None

    # Level 3: Block (if confirmed)
    btc_height: Optional[int] = None
    btc_hash: Optional[bytes] = None
    btc_timestamp: Optional[int] = None
    btc_confirmations: int = 0
    btc_finality: FinalityState = FinalityState.UNKNOWN

    # Level 4/5/6: System state
    current_level: AdamLevel = AdamLevel.BITCOIN_ACTIVE
    vdf_active: bool = False
    vdf_sequence: Optional[int] = None

    # Metadata
    sequence: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'level': self.current_level.name,
            'ntp_servers': self.ntp_servers_responding,
            'utc_time': self.utc_time,
            'clock_drift_ms': round(self.clock_drift_ms, 2),
            'btc_height': self.btc_height,
            'btc_hash': self.btc_hash.hex()[:16] + '...' if self.btc_hash else None,
            'btc_finality': self.btc_finality.name,
            'btc_confirmations': self.btc_confirmations,
            'vdf_active': self.vdf_active,
            'sequence': self.sequence
        }


# ============================================================================
# LEVEL 0: NTP SERVERS
# ============================================================================

class Level0_NTPServers:
    """
    Level 0: External NTP Server Synchronization

    Queries multiple NTP servers, calculates weighted average.
    Provides reference time for Level 1 calibration.
    """

    def __init__(self, servers: List[str] = None):
        self.servers = servers or NTP_SERVERS.copy()
        self.state = LevelState.INACTIVE
        self.last_results: List[Level0Result] = []
        self.consensus_offset_ms: float = 0.0

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        logger.info(f"Level 0 (NTP) initialized with {len(self.servers)} servers")

    def start(self):
        """Start NTP synchronization."""
        if self._running:
            return
        self._running = True
        self.state = LevelState.SYNCING
        self._thread = threading.Thread(target=self._sync_loop, daemon=True, name="Adam-L0-NTP")
        self._thread.start()
        logger.info("Level 0 (NTP) started")

    def stop(self):
        """Stop NTP synchronization."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.state = LevelState.INACTIVE
        logger.info("Level 0 (NTP) stopped")

    def _sync_loop(self):
        """Background NTP sync loop."""
        while self._running:
            try:
                self._sync_once()
            except Exception as e:
                logger.error(f"Level 0 sync error: {e}")
                self.state = LevelState.DEGRADED
            time.sleep(NTP_SYNC_INTERVAL)

    def _sync_once(self):
        """Query all NTP servers once."""
        results = []
        for server in self.servers[:5]:  # Max 5 servers
            result = self._query_ntp(server)
            if result:
                results.append(result)

        with self._lock:
            self.last_results = results

            if len(results) >= NTP_MIN_SERVERS:
                # Weighted average by confidence
                total_weight = sum(r.confidence for r in results)
                if total_weight > 0:
                    self.consensus_offset_ms = sum(
                        r.offset_ms * r.confidence for r in results
                    ) / total_weight
                self.state = LevelState.ACTIVE
            else:
                self.state = LevelState.DEGRADED
                logger.warning(f"Level 0: Only {len(results)}/{NTP_MIN_SERVERS} NTP servers responded")

    def _query_ntp(self, server: str) -> Optional[Level0Result]:
        """Query single NTP server."""
        try:
            ntp_data = b'\x1b' + 47 * b'\0'
            start = time.time()

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(NTP_TIMEOUT_SEC)
            try:
                sock.sendto(ntp_data, (server, 123))
                data, _ = sock.recvfrom(48)
                end = time.time()

                if len(data) >= 44:
                    ntp_timestamp = struct.unpack('!I', data[40:44])[0]
                    ntp_time = ntp_timestamp - 2208988800  # NTP to Unix epoch
                    round_trip = (end - start) * 1000
                    offset = (ntp_time - start) * 1000

                    return Level0Result(
                        server=server,
                        ntp_time=ntp_time,
                        round_trip_ms=round_trip,
                        offset_ms=offset,
                        confidence=1.0 / (1.0 + round_trip / 100.0),
                        queried_at=start
                    )
            finally:
                sock.close()
        except Exception as e:
            logger.debug(f"Level 0: NTP query to {server} failed: {e}")
        return None

    def get_offset(self) -> float:
        """Get consensus offset in milliseconds."""
        with self._lock:
            return self.consensus_offset_ms

    def get_servers_count(self) -> int:
        """Get number of responding servers."""
        with self._lock:
            return len(self.last_results)

    def get_status(self) -> Dict[str, Any]:
        """Get level status."""
        with self._lock:
            return {
                'level': 0,
                'name': 'NTP_SERVERS',
                'state': self.state.name,
                'servers_responding': len(self.last_results),
                'servers_total': len(self.servers),
                'consensus_offset_ms': round(self.consensus_offset_ms, 2)
            }


# ============================================================================
# LEVEL 1: NODE UTC
# ============================================================================

class Level1_NodeUTC:
    """
    Level 1: Node Hardware Clock (UTC)

    Local system clock calibrated against Level 0 NTP.
    Tracks drift and provides corrected UTC time.
    """

    def __init__(self, level0: Level0_NTPServers):
        self.level0 = level0
        self.state = LevelState.INACTIVE

        self.offset_ms: float = 0.0
        self.drift_history: deque = deque(maxlen=60)  # 1 hour of drift data
        self.last_sync: float = 0.0

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        logger.info("Level 1 (Node UTC) initialized")

    def start(self):
        """Start UTC tracking."""
        if self._running:
            return
        self._running = True
        self.state = LevelState.SYNCING
        self._thread = threading.Thread(target=self._track_loop, daemon=True, name="Adam-L1-UTC")
        self._thread.start()
        logger.info("Level 1 (Node UTC) started")

    def stop(self):
        """Stop UTC tracking."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.state = LevelState.INACTIVE
        logger.info("Level 1 (Node UTC) stopped")

    def _track_loop(self):
        """Track clock drift."""
        while self._running:
            try:
                with self._lock:
                    new_offset = self.level0.get_offset()

                    if self.offset_ms != 0:
                        drift = new_offset - self.offset_ms
                        self.drift_history.append(drift)

                        if abs(drift) > MAX_CLOCK_DRIFT_MS:
                            logger.warning(f"Level 1: Large clock drift {drift:.1f}ms")

                    self.offset_ms = new_offset
                    self.last_sync = time.time()
                    self.state = LevelState.ACTIVE

            except Exception as e:
                logger.error(f"Level 1 error: {e}")
                self.state = LevelState.DEGRADED

            time.sleep(DRIFT_CORRECTION_INTERVAL)

    def get_utc(self) -> float:
        """Get corrected UTC time."""
        with self._lock:
            return time.time() + (self.offset_ms / 1000.0)

    def get_local(self) -> float:
        """Get local system time."""
        return time.time()

    def get_drift_rate(self) -> float:
        """Get drift rate in ms/minute."""
        with self._lock:
            if len(self.drift_history) < 2:
                return 0.0
            return statistics.mean(self.drift_history)

    def get_state(self) -> Level1State:
        """Get current level 1 state."""
        with self._lock:
            return Level1State(
                utc_time=self.get_utc(),
                local_time=time.time(),
                offset_ms=self.offset_ms,
                drift_rate_ms_min=self.get_drift_rate(),
                last_sync=self.last_sync,
                synced=self.state == LevelState.ACTIVE
            )

    def get_status(self) -> Dict[str, Any]:
        """Get level status."""
        with self._lock:
            return {
                'level': 1,
                'name': 'NODE_UTC',
                'state': self.state.name,
                'offset_ms': round(self.offset_ms, 2),
                'drift_rate_ms_min': round(self.get_drift_rate(), 3),
                'last_sync': self.last_sync
            }


# ============================================================================
# LEVEL 2: MEMPOOL TIME
# ============================================================================

class Level2_MempoolTime:
    """
    Level 2: Bitcoin Mempool Observation

    Tracks when transactions first appear in mempool.
    Provides PENDING finality state.
    """

    def __init__(self, level1: Level1_NodeUTC):
        self.level1 = level1
        self.state = LevelState.INACTIVE
        self.mempool = Level2State(tx_count=0, size_bytes=0, fee_min=0, fee_median=0, fee_high=0)

        self._lock = threading.Lock()
        self._running = False

        logger.info("Level 2 (Mempool) initialized")

    def start(self):
        """Start mempool tracking."""
        self._running = True
        self.state = LevelState.ACTIVE
        logger.info("Level 2 (Mempool) started")

    def stop(self):
        """Stop mempool tracking."""
        self._running = False
        self.state = LevelState.INACTIVE
        logger.info("Level 2 (Mempool) stopped")

    def on_tx_seen(self, tx_hash: bytes) -> float:
        """
        Record when transaction first seen in mempool.

        Returns timestamp when TX was first observed.
        """
        with self._lock:
            if tx_hash not in self.mempool.first_seen:
                first_seen = self.level1.get_utc()
                self.mempool.first_seen[tx_hash] = first_seen
                logger.debug(f"Level 2: TX {tx_hash.hex()[:16]}... first seen at {first_seen}")
                return first_seen
            return self.mempool.first_seen[tx_hash]

    def get_tx_first_seen(self, tx_hash: bytes) -> Optional[float]:
        """Get when TX was first seen, or None."""
        with self._lock:
            return self.mempool.first_seen.get(tx_hash)

    def update_mempool_state(
        self,
        tx_count: int,
        size_bytes: int,
        fee_min: float,
        fee_median: float,
        fee_high: float
    ):
        """Update mempool statistics."""
        with self._lock:
            self.mempool.tx_count = tx_count
            self.mempool.size_bytes = size_bytes
            self.mempool.fee_min = fee_min
            self.mempool.fee_median = fee_median
            self.mempool.fee_high = fee_high
            self.mempool.last_update = self.level1.get_utc()

    def clear_confirmed(self, tx_hashes: List[bytes]):
        """Remove confirmed TXs from tracking."""
        with self._lock:
            for tx_hash in tx_hashes:
                self.mempool.first_seen.pop(tx_hash, None)

    def get_status(self) -> Dict[str, Any]:
        """Get level status."""
        with self._lock:
            return {
                'level': 2,
                'name': 'MEMPOOL_TIME',
                'state': self.state.name,
                'tx_count': self.mempool.tx_count,
                'size_mb': round(self.mempool.size_bytes / 1_000_000, 2),
                'fee_median': self.mempool.fee_median,
                'tracked_txs': len(self.mempool.first_seen),
                'last_update': self.mempool.last_update
            }


# ============================================================================
# LEVEL 3: BLOCK TIME
# ============================================================================

class Level3_BlockTime:
    """
    Level 3: Bitcoin Block Confirmation

    Tracks Bitcoin blocks and finality progression:
    PENDING → TENTATIVE → CONFIRMED → IRREVERSIBLE
    """

    def __init__(self, level1: Level1_NodeUTC, level2: Level2_MempoolTime):
        self.level1 = level1
        self.level2 = level2
        self.state = LevelState.INACTIVE

        self.chain_height: int = 0
        self.last_block: Optional[Level3Block] = None
        self.last_block_time: Optional[float] = None
        self.blocks: Dict[int, Level3Block] = {}
        self.max_blocks = 200

        # Callbacks
        self.on_new_block: Optional[Callable[[Level3Block], None]] = None
        self.on_finality_change: Optional[Callable[[int, FinalityState], None]] = None

        self._lock = threading.RLock()

        logger.info("Level 3 (Block Time) initialized")

    def start(self):
        """Start block tracking."""
        self.state = LevelState.SYNCING
        logger.info("Level 3 (Block Time) started")

    def stop(self):
        """Stop block tracking."""
        self.state = LevelState.INACTIVE
        logger.info("Level 3 (Block Time) stopped")

    def on_block(
        self,
        height: int,
        block_hash: bytes,
        prev_hash: bytes,
        timestamp: int,
        merkle_root: bytes = b'\x00' * 32,
        tx_hashes: List[bytes] = None
    ) -> Level3Block:
        """
        Process new Bitcoin block.

        This is THE entry point for Bitcoin blocks in Montana.
        """
        with self._lock:
            block = Level3Block(
                height=height,
                hash=block_hash,
                prev_hash=prev_hash,
                timestamp=timestamp,
                merkle_root=merkle_root,
                confirmations=1,
                finality=FinalityState.TENTATIVE,
                received_at=self.level1.get_utc()
            )

            # Update chain state
            self.chain_height = max(self.chain_height, height)
            self.last_block = block
            self.last_block_time = self.level1.get_utc()
            self.blocks[height] = block
            self.state = LevelState.ACTIVE

            # Clean old blocks
            while len(self.blocks) > self.max_blocks:
                oldest = min(self.blocks.keys())
                del self.blocks[oldest]

            # Update finality for all blocks
            self._update_all_finality()

            # Clear confirmed TXs from mempool tracking
            if tx_hashes:
                self.level2.clear_confirmed(tx_hashes)

            logger.info(
                f"Level 3: Block #{height} ({block.hash_hex[:16]}...) "
                f"finality={block.finality.name}"
            )

            # Callback
            if self.on_new_block:
                try:
                    self.on_new_block(block)
                except Exception as e:
                    logger.error(f"Level 3 block callback error: {e}")

            return block

    def _update_all_finality(self):
        """Update finality for all tracked blocks."""
        for height, block in self.blocks.items():
            old_finality = block.finality
            block.update_finality(self.chain_height)

            if block.finality != old_finality and self.on_finality_change:
                try:
                    self.on_finality_change(height, block.finality)
                    logger.debug(f"Level 3: Block #{height} finality: {old_finality.name} → {block.finality.name}")
                except Exception as e:
                    logger.error(f"Level 3 finality callback error: {e}")

    def get_finality(self, height: int) -> FinalityState:
        """Get finality state for block height."""
        with self._lock:
            if height > self.chain_height:
                return FinalityState.UNKNOWN
            if height in self.blocks:
                return self.blocks[height].finality
            # Old block not in cache
            confirmations = self.chain_height - height + 1
            return FinalityState.from_confirmations(confirmations)

    def get_confirmations(self, height: int) -> int:
        """Get confirmation count for block height."""
        with self._lock:
            if height > self.chain_height:
                return 0
            return self.chain_height - height + 1

    def is_irreversible(self, height: int) -> bool:
        """Check if block is irreversibly final."""
        return self.get_finality(height) == FinalityState.IRREVERSIBLE

    def time_since_last_block(self) -> Optional[float]:
        """Seconds since last block."""
        with self._lock:
            if self.last_block_time is None:
                return None
            return self.level1.get_utc() - self.last_block_time

    def is_producing(self) -> bool:
        """Is Bitcoin producing blocks normally?"""
        with self._lock:
            if self.last_block_time is None:
                return False
            return self.time_since_last_block() < BITCOIN_MAX_VARIANCE

    def get_status(self) -> Dict[str, Any]:
        """Get level status."""
        with self._lock:
            return {
                'level': 3,
                'name': 'BLOCK_TIME',
                'state': self.state.name,
                'chain_height': self.chain_height,
                'last_block_hash': self.last_block.hash_hex[:16] + '...' if self.last_block else None,
                'last_block_finality': self.last_block.finality.name if self.last_block else None,
                'seconds_since_block': self.time_since_last_block(),
                'is_producing': self.is_producing(),
                'tracked_blocks': len(self.blocks)
            }


# ============================================================================
# LEVELS 4-5-6: SYSTEM STATE (Bitcoin Active / VDF Fallback / VDF Deactivate)
# ============================================================================

class Level456_SystemState:
    """
    Levels 4-5-6: System State Management

    Level 4: BITCOIN_ACTIVE - Normal operation, VDF idle
    Level 5: VDF_FALLBACK - Bitcoin down, VDF provides time
    Level 6: VDF_DEACTIVATE - Bitcoin back, VDF turns off
    """

    def __init__(self, level3: Level3_BlockTime, vdf_iterations: int = 1000):
        self.level3 = level3
        self.vdf_iterations = vdf_iterations

        self.current_level: AdamLevel = AdamLevel.BITCOIN_ACTIVE
        self.vdf_active: bool = False
        self.vdf_activation_reason: Optional[str] = None
        self.vdf_activation_time: Optional[float] = None
        self.vdf_sequence: int = 0
        self.vdf_last_hash: Optional[bytes] = None

        # VDF engine (lazy loaded)
        self._vdf_engine = None

        self._lock = threading.Lock()

        logger.info("Levels 4-5-6 (System State) initialized")

    def _get_vdf_engine(self):
        """Lazy load VDF engine."""
        if self._vdf_engine is None:
            try:
                from pantheon.athena.vdf_fallback import VDFFallback
                self._vdf_engine = VDFFallback(iterations=self.vdf_iterations)
            except ImportError:
                logger.error("VDF Fallback module not available!")
        return self._vdf_engine

    def check_state(self) -> AdamLevel:
        """
        Check and update system state.

        Level 4 → Level 5: If Bitcoin down for 2+ blocks
        Level 5 → Level 6 → Level 4: If Bitcoin resumes
        """
        with self._lock:
            time_since = self.level3.time_since_last_block()

            if self.current_level == AdamLevel.BITCOIN_ACTIVE:
                # Check if need to switch to VDF
                if time_since is not None and time_since >= VDF_TRIGGER_SECONDS:
                    self._activate_vdf(
                        f"Bitcoin unavailable: {int(time_since / 60)} min "
                        f"since last block (trigger: {VDF_TRIGGER_SECONDS // 60} min)"
                    )

            elif self.current_level == AdamLevel.VDF_FALLBACK:
                # Check if Bitcoin is back
                if self.level3.is_producing():
                    self._deactivate_vdf("Bitcoin resumed producing blocks")

            return self.current_level

    def _activate_vdf(self, reason: str):
        """Activate VDF fallback (Level 4 → Level 5)."""
        logger.warning(f"LEVEL 5 ACTIVATED: {reason}")

        self.current_level = AdamLevel.VDF_FALLBACK
        self.vdf_active = True
        self.vdf_activation_reason = reason
        self.vdf_activation_time = time.time()

        # Start VDF engine
        vdf = self._get_vdf_engine()
        if vdf:
            vdf.activate(reason)

    def _deactivate_vdf(self, reason: str):
        """Deactivate VDF (Level 5 → Level 6 → Level 4)."""
        logger.info(f"LEVEL 6 TRIGGERED: {reason}")

        # Briefly at Level 6
        self.current_level = AdamLevel.VDF_DEACTIVATE

        # Stop VDF
        if self._vdf_engine:
            self._vdf_engine.deactivate(reason)

        self.vdf_active = False

        # Return to Level 4
        self.current_level = AdamLevel.BITCOIN_ACTIVE
        logger.info("LEVEL 4 RESTORED: Bitcoin active, VDF idle")

    def compute_vdf_timestamp(self) -> Optional[Tuple[int, bytes]]:
        """Compute VDF timestamp if in fallback mode."""
        with self._lock:
            if not self.vdf_active:
                return None

            vdf = self._get_vdf_engine()
            if not vdf:
                return None

            ts = vdf.compute_timestamp()
            if ts:
                self.vdf_sequence = ts.sequence
                self.vdf_last_hash = ts.hash()
                return ts.sequence, ts.hash()

            return None

    def get_status(self) -> Dict[str, Any]:
        """Get levels 4-5-6 status."""
        with self._lock:
            return {
                'levels': '4-5-6',
                'name': 'SYSTEM_STATE',
                'current_level': self.current_level.name,
                'vdf_active': self.vdf_active,
                'vdf_activation_reason': self.vdf_activation_reason,
                'vdf_sequence': self.vdf_sequence
            }


# ============================================================================
# ADAM SYNC: THE MASTER CLASS
# ============================================================================

class AdamSync:
    """
    Adam Sync: THE CANONICAL TIME SYNCHRONIZATION FOR MONTANA

    This is the ONLY class that should be used for time synchronization.
    All other time-related code MUST go through Adam Sync.

    Integrates all 7 levels (0-6) into a unified interface.
    """

    def __init__(self, vdf_iterations: int = 1000, auto_start: bool = False):
        """
        Initialize Adam Sync.

        Args:
            vdf_iterations: VDF iterations for Level 5 fallback
            auto_start: Start all levels automatically
        """
        # Initialize all levels
        self.level0 = Level0_NTPServers()
        self.level1 = Level1_NodeUTC(self.level0)
        self.level2 = Level2_MempoolTime(self.level1)
        self.level3 = Level3_BlockTime(self.level1, self.level2)
        self.level456 = Level456_SystemState(self.level3, vdf_iterations)

        self.sequence: int = 0
        self._lock = threading.RLock()
        self._started = False

        logger.info("═" * 60)
        logger.info("ADAM SYNC INITIALIZED - THE CANONICAL TIME SOURCE")
        logger.info("═" * 60)

        if auto_start:
            self.start()

    def start(self):
        """Start all Adam Sync levels."""
        if self._started:
            return

        self.level0.start()
        self.level1.start()
        self.level2.start()
        self.level3.start()

        self._started = True
        logger.info("ADAM SYNC STARTED - All levels active")

    def stop(self):
        """Stop all Adam Sync levels."""
        if not self._started:
            return

        self.level0.stop()
        self.level1.stop()
        self.level2.stop()
        self.level3.stop()

        self._started = False
        logger.info("ADAM SYNC STOPPED")

    # =========================================================================
    # PRIMARY API
    # =========================================================================

    def on_bitcoin_block(
        self,
        height: int,
        block_hash: bytes,
        prev_hash: bytes,
        timestamp: int,
        merkle_root: bytes = b'\x00' * 32,
        tx_hashes: List[bytes] = None
    ) -> Level3Block:
        """
        Process new Bitcoin block.

        THIS IS THE ONLY ENTRY POINT FOR BITCOIN BLOCKS.
        """
        block = self.level3.on_block(
            height, block_hash, prev_hash, timestamp, merkle_root, tx_hashes
        )

        # Check system state after new block
        self.level456.check_state()

        return block

    def on_tx_seen(self, tx_hash: bytes) -> float:
        """
        Record transaction seen in mempool.

        Returns timestamp when TX was first observed.
        """
        return self.level2.on_tx_seen(tx_hash)

    def get_timestamp(self) -> AdamTimestamp:
        """
        Get current Adam Sync timestamp.

        THIS IS THE ONLY WAY TO GET TIME IN MONTANA.
        """
        with self._lock:
            # Check system state
            self.level456.check_state()

            ts = AdamTimestamp(
                # Level 0
                ntp_servers_responding=self.level0.get_servers_count(),
                ntp_consensus_offset_ms=self.level0.get_offset(),

                # Level 1
                utc_time=self.level1.get_utc(),
                local_time=self.level1.get_local(),
                clock_drift_ms=self.level1.get_drift_rate(),

                # Level 3
                btc_height=self.level3.chain_height if self.level3.chain_height > 0 else None,
                btc_hash=self.level3.last_block.hash if self.level3.last_block else None,
                btc_timestamp=self.level3.last_block.timestamp if self.level3.last_block else None,
                btc_confirmations=1 if self.level3.last_block else 0,
                btc_finality=self.level3.last_block.finality if self.level3.last_block else FinalityState.UNKNOWN,

                # Level 4-5-6
                current_level=self.level456.current_level,
                vdf_active=self.level456.vdf_active,
                vdf_sequence=self.level456.vdf_sequence if self.level456.vdf_active else None,

                sequence=self.sequence
            )

            self.sequence += 1
            return ts

    def get_utc(self) -> float:
        """Get current UTC time (Level 1)."""
        return self.level1.get_utc()

    def get_finality(self, height: int) -> FinalityState:
        """Get finality state for Bitcoin block height."""
        return self.level3.get_finality(height)

    def is_irreversible(self, height: int) -> bool:
        """Check if block is irreversibly final."""
        return self.level3.is_irreversible(height)

    def get_current_level(self) -> AdamLevel:
        """Get current Adam level (4, 5, or 6)."""
        return self.level456.current_level

    def is_bitcoin_active(self) -> bool:
        """Is Bitcoin producing blocks? (Level 4)"""
        return self.level456.current_level == AdamLevel.BITCOIN_ACTIVE

    def is_vdf_active(self) -> bool:
        """Is VDF fallback active? (Level 5)"""
        return self.level456.vdf_active

    def get_status(self) -> Dict[str, Any]:
        """Get complete Adam Sync status."""
        with self._lock:
            return {
                'adam_sync': 'CANONICAL TIME SOURCE',
                'started': self._started,
                'sequence': self.sequence,
                'current_level': self.level456.current_level.name,
                'levels': {
                    0: self.level0.get_status(),
                    1: self.level1.get_status(),
                    2: self.level2.get_status(),
                    3: self.level3.get_status(),
                    '4-5-6': self.level456.get_status()
                }
            }


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test():
    """Run Adam Sync self-tests."""
    import hashlib

    logger.info("=" * 60)
    logger.info("ADAM SYNC SELF-TEST")
    logger.info("=" * 60)

    # Test FinalityState
    assert FinalityState.from_confirmations(0) == FinalityState.PENDING
    assert FinalityState.from_confirmations(1) == FinalityState.TENTATIVE
    assert FinalityState.from_confirmations(6) == FinalityState.CONFIRMED
    assert FinalityState.from_confirmations(100) == FinalityState.IRREVERSIBLE
    logger.info("✓ FinalityState transitions")

    # Test AdamLevel
    assert AdamLevel.NTP_SERVERS == 0
    assert AdamLevel.NODE_UTC == 1
    assert AdamLevel.MEMPOOL_TIME == 2
    assert AdamLevel.BLOCK_TIME == 3
    assert AdamLevel.BITCOIN_ACTIVE == 4
    assert AdamLevel.VDF_FALLBACK == 5
    assert AdamLevel.VDF_DEACTIVATE == 6
    logger.info("✓ AdamLevel values")

    # Test Level3Block
    block = Level3Block(
        height=840000,
        hash=hashlib.sha256(b"block").digest(),
        prev_hash=hashlib.sha256(b"prev").digest(),
        timestamp=int(time.time()),
        merkle_root=hashlib.sha256(b"merkle").digest()
    )
    block.update_finality(840010)
    assert block.confirmations == 11
    assert block.finality == FinalityState.CONFIRMED
    logger.info("✓ Level3Block finality")

    # Test serialization
    serialized = block.serialize()
    deserialized, _ = Level3Block.deserialize(serialized)
    assert deserialized.height == block.height
    assert deserialized.hash == block.hash
    logger.info("✓ Level3Block serialization")

    # Test AdamSync (without NTP - would timeout)
    adam = AdamSync(vdf_iterations=50, auto_start=False)

    # Start only non-network levels
    adam.level1._running = True
    adam.level1.state = LevelState.ACTIVE
    adam.level2.start()
    adam.level3.start()

    # Simulate Bitcoin blocks
    for i in range(5):
        adam.on_bitcoin_block(
            height=840000 + i,
            block_hash=hashlib.sha256(f"block_{i}".encode()).digest(),
            prev_hash=hashlib.sha256(f"block_{i-1}".encode()).digest() if i > 0 else b'\x00' * 32,
            timestamp=int(time.time()) - (5 - i) * 600
        )

    assert adam.level3.chain_height == 840004
    assert adam.level456.current_level == AdamLevel.BITCOIN_ACTIVE
    logger.info("✓ Block processing")

    # Get timestamp
    ts = adam.get_timestamp()
    assert ts.btc_height == 840004
    assert ts.current_level == AdamLevel.BITCOIN_ACTIVE
    logger.info("✓ AdamTimestamp")

    # Check finality
    assert adam.get_finality(840000) == FinalityState.TENTATIVE
    assert adam.get_finality(840004) == FinalityState.TENTATIVE
    logger.info("✓ Finality queries")

    # Test mempool tracking
    tx_hash = hashlib.sha256(b"test_tx").digest()
    first_seen = adam.on_tx_seen(tx_hash)
    assert first_seen > 0
    assert adam.level2.get_tx_first_seen(tx_hash) == first_seen
    logger.info("✓ Mempool TX tracking")

    # Get status
    status = adam.get_status()
    assert 'levels' in status
    assert 0 in status['levels']
    assert 1 in status['levels']
    assert 2 in status['levels']
    assert 3 in status['levels']
    assert '4-5-6' in status['levels']
    logger.info("✓ Status reporting")

    logger.info("=" * 60)
    logger.info("ALL ADAM SYNC TESTS PASSED!")
    logger.info("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
