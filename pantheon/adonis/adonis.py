"""
Adonis - Advanced Reputation System for Proof of Time
Multi-factor reputation model with behavioral analysis and trust dynamics.

The Adonis system extends the basic f_rep component with:
- Multi-dimensional reputation scoring
- Behavioral pattern analysis
- Trust graph propagation
- Dynamic penalty/reward mechanisms
- Historical decay and recovery

Named after Adonis - symbolizing the pursuit of perfection through time.

Time is the ultimate proof.
"""

import time
import math
import struct
import logging
import threading
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import IntEnum, auto
from collections import defaultdict

from pantheon.prometheus import sha256
from config import PROTOCOL

logger = logging.getLogger("proof_of_time.adonis")


# ============================================================================
# CONSTANTS
# ============================================================================

# Maximum vouches per node per day (rate limiting)
MAX_VOUCHES_PER_DAY = 10

# Profile expiration (1 year without events = garbage collected)
PROFILE_EXPIRATION_SECONDS = 365 * 86400

# Maximum allowed timestamp drift (10 minutes into future)
MAX_TIMESTAMP_DRIFT = 600


# ============================================================================
# REPUTATION DIMENSIONS
# ============================================================================

class ReputationDimension(IntEnum):
    """
    The Five Fingers of Adonis - unified node scoring system.

    Adonis is the ONLY formula for node weight calculation.
    No separate f_time/f_space/f_rep - everything is here.

    Five Fingers (like a hand):
    - THUMB (TIME): The opposable finger - makes the hand work (50%)
    - INDEX (INTEGRITY): Points the way - moral compass (20%)
    - MIDDLE (STORAGE): Central support - network backbone (15%)
    - RING (GEOGRAPHY): Global commitment - country + city (10%)
    - PINKY (HANDSHAKE): Elite bonus - mutual trust between veterans (5%)

    HANDSHAKE unlocks only when first 4 fingers are saturated.
    Two veterans shake hands = cryptographic proof of trust.
    """
    TIME = auto()          # THUMB: Continuous uptime - saturates at 180 days (50%)
    INTEGRITY = auto()     # INDEX: No violations, valid proofs (20%)
    STORAGE = auto()       # MIDDLE: Chain storage - saturates at 100% (15%)
    GEOGRAPHY = auto()     # RING: Country + city diversity (10%)
    HANDSHAKE = auto()     # PINKY: Mutual trust - saturates at 10 handshakes (5%)


@dataclass
class DimensionScore:
    """Score for a single reputation dimension."""
    value: float = 0.0        # Current score [0, 1]
    confidence: float = 0.0   # Confidence in this score [0, 1]
    samples: int = 0          # Number of observations
    last_update: int = 0      # Last update timestamp

    def update(self, observation: float, weight: float = 1.0, timestamp: int = 0):
        """
        Update dimension score with new observation.

        Uses exponential moving average for smoothing.
        """
        if timestamp == 0:
            timestamp = int(time.time())

        # Decay factor based on time since last update
        if self.last_update > 0:
            age_hours = (timestamp - self.last_update) / 3600
            decay = math.exp(-age_hours / 168)  # 1-week half-life
        else:
            decay = 0.0

        # Update score with weighted moving average
        alpha = weight / (self.samples + weight) if self.samples > 0 else 1.0
        self.value = (1 - alpha) * self.value * decay + alpha * observation
        self.value = max(0.0, min(1.0, self.value))

        # Update confidence
        self.samples += 1
        self.confidence = 1 - math.exp(-self.samples / 100)  # Saturates at ~100 samples

        self.last_update = timestamp


# ============================================================================
# REPUTATION EVENTS
# ============================================================================

class ReputationEvent(IntEnum):
    """Events that affect reputation."""
    # Positive events
    BLOCK_PRODUCED = auto()      # Successfully produced a block
    BLOCK_VALIDATED = auto()     # Validated a block correctly
    TX_RELAYED = auto()          # Relayed valid transaction
    UPTIME_CHECKPOINT = auto()   # Maintained uptime (hourly)
    STORAGE_UPDATE = auto()      # Storage percentage updated
    NEW_COUNTRY = auto()         # First node from a new country (big bonus)
    NEW_CITY = auto()            # First node from a new city
    HANDSHAKE_FORMED = auto()    # Mutual handshake with another veteran

    # Negative events
    BLOCK_INVALID = auto()       # Produced invalid block
    VRF_INVALID = auto()         # Invalid VRF proof
    VDF_INVALID = auto()         # Invalid VDF proof
    EQUIVOCATION = auto()        # Double-signing
    DOWNTIME = auto()            # Extended offline period
    SPAM_DETECTED = auto()       # Transaction spam
    HANDSHAKE_BROKEN = auto()    # Handshake partner penalized or offline


@dataclass
class ReputationRecord:
    """Record of a reputation event."""
    event_type: ReputationEvent
    timestamp: int
    impact: float              # Positive or negative impact
    source: Optional[bytes]    # Source node (for peer events)
    evidence: Optional[bytes]  # Hash of evidence
    height: int = 0            # Block height when event occurred

    def serialize(self) -> bytes:
        """Serialize record for storage."""
        data = bytearray()
        data.extend(struct.pack('<B', self.event_type))
        data.extend(struct.pack('<Q', self.timestamp))
        data.extend(struct.pack('<f', self.impact))
        data.extend(struct.pack('<Q', self.height))
        data.extend(self.source or b'\x00' * 32)
        data.extend(self.evidence or b'\x00' * 32)
        return bytes(data)

    @classmethod
    def deserialize(cls, data: bytes) -> 'ReputationRecord':
        """Deserialize record from bytes."""
        event_type = struct.unpack('<B', data[0:1])[0]
        timestamp = struct.unpack('<Q', data[1:9])[0]
        impact = struct.unpack('<f', data[9:13])[0]
        height = struct.unpack('<Q', data[13:21])[0]
        source = data[21:53] if data[21:53] != b'\x00' * 32 else None
        evidence = data[53:85] if data[53:85] != b'\x00' * 32 else None

        return cls(
            event_type=ReputationEvent(event_type),
            timestamp=timestamp,
            impact=impact,
            height=height,
            source=source,
            evidence=evidence
        )


# ============================================================================
# HANDSHAKE - MUTUAL TRUST BETWEEN VETERANS
# ============================================================================

@dataclass
class Handshake:
    """
    Cryptographic proof of mutual trust between two veteran nodes.

    A handshake can only form when BOTH nodes have saturated their
    first 4 fingers (TIME, INTEGRITY, STORAGE, GEOGRAPHY).

    This is the PINKY finger - the elite bonus that completes the hand.
    """
    node_a: bytes              # First node pubkey
    node_b: bytes              # Second node pubkey
    created_at: int            # Block height when formed
    sig_a: bytes               # Signature from node A
    sig_b: bytes               # Signature from node B

    def __post_init__(self):
        # Ensure canonical ordering (smaller pubkey first)
        if self.node_a > self.node_b:
            self.node_a, self.node_b = self.node_b, self.node_a
            self.sig_a, self.sig_b = self.sig_b, self.sig_a

    def get_id(self) -> bytes:
        """Get unique handshake ID."""
        return sha256(self.node_a + self.node_b)

    def involves(self, pubkey: bytes) -> bool:
        """Check if this handshake involves the given node."""
        return pubkey == self.node_a or pubkey == self.node_b

    def get_partner(self, pubkey: bytes) -> Optional[bytes]:
        """Get the partner node in this handshake."""
        if pubkey == self.node_a:
            return self.node_b
        elif pubkey == self.node_b:
            return self.node_a
        return None


# ============================================================================
# NODE REPUTATION PROFILE
# ============================================================================

@dataclass
class AdonisProfile:
    """
    Complete reputation profile for a node.

    Combines multi-dimensional scoring with behavioral history
    to create a comprehensive trust assessment.
    """
    pubkey: bytes

    # Multi-dimensional scores
    dimensions: Dict[ReputationDimension, DimensionScore] = field(
        default_factory=lambda: {dim: DimensionScore() for dim in ReputationDimension}
    )

    # Aggregate score (weighted combination of dimensions)
    aggregate_score: float = 0.0

    # Historical records (limited to recent history)
    history: List[ReputationRecord] = field(default_factory=list)
    max_history: int = 1000

    # Trust relationships
    trusted_by: Set[bytes] = field(default_factory=set)   # Nodes that vouch for us
    trusts: Set[bytes] = field(default_factory=set)       # Nodes we vouch for

    # Status flags
    is_penalized: bool = False
    penalty_until: int = 0
    penalty_reason: str = ""

    # Metadata
    created_at: int = 0
    last_updated: int = 0
    total_events: int = 0

    # Geographic diversity
    country_code: Optional[str] = None  # ISO country code (e.g., "US", "DE", "JP")
    city_hash: Optional[bytes] = None   # SHA256(country + city) - no raw IP stored

    # Handshakes (PINKY finger) - set of partner pubkeys
    handshake_partners: Set[bytes] = field(default_factory=set)

    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = int(time.time())
        if not self.dimensions:
            self.dimensions = {dim: DimensionScore() for dim in ReputationDimension}

    def get_dimension_score(self, dimension: ReputationDimension) -> float:
        """Get score for a specific dimension."""
        return self.dimensions[dimension].value

    def get_trust_score(self) -> float:
        """
        Calculate trust score from peer vouches.

        Score increases with number of vouches, but with diminishing returns.
        """
        if not self.trusted_by:
            return 0.0

        n = len(self.trusted_by)
        # Logarithmic scaling: 1 vouch = 0.2, 10 vouches = 0.6, 100 vouches = 0.9
        return min(1.0, 0.2 * math.log10(1 + n * 4))

    def compute_aggregate(self, weights: Optional[Dict[ReputationDimension, float]] = None) -> float:
        """
        Compute aggregate reputation score.

        Uses the Five Fingers of Adonis weights.
        """
        if weights is None:
            weights = {
                ReputationDimension.TIME: 0.50,        # THUMB
                ReputationDimension.INTEGRITY: 0.20,   # INDEX
                ReputationDimension.STORAGE: 0.15,     # MIDDLE
                ReputationDimension.GEOGRAPHY: 0.10,   # RING (country + city)
                ReputationDimension.HANDSHAKE: 0.05,   # PINKY (mutual trust)
            }

        total = 0.0
        weight_sum = 0.0

        for dim, weight in weights.items():
            score = self.dimensions[dim]
            # Weight by confidence
            effective_weight = weight * score.confidence
            total += score.value * effective_weight
            weight_sum += effective_weight

        if weight_sum > 0:
            self.aggregate_score = total / weight_sum
        else:
            self.aggregate_score = 0.0

        return self.aggregate_score

    def add_event(self, record: ReputationRecord):
        """Add a reputation event to history."""
        self.history.append(record)
        self.total_events += 1
        self.last_updated = record.timestamp

        # Prune old history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_recent_events(self, since: int = 0, limit: int = 100) -> List[ReputationRecord]:
        """Get recent events since timestamp."""
        if since == 0:
            since = int(time.time()) - 86400 * 7  # Last 7 days

        recent = [e for e in self.history if e.timestamp >= since]
        return recent[-limit:]

    def apply_penalty(self, duration_seconds: int, reason: str):
        """Apply a time-based penalty."""
        current_time = int(time.time())
        self.is_penalized = True
        self.penalty_until = current_time + duration_seconds
        self.penalty_reason = reason

        logger.warning(
            f"Penalty applied to {self.pubkey.hex()[:16]}...: "
            f"{reason}, until {self.penalty_until}"
        )

    def check_penalty(self, current_time: Optional[int] = None) -> bool:
        """Check if penalty is still active."""
        if current_time is None:
            current_time = int(time.time())

        if self.is_penalized and current_time >= self.penalty_until:
            self.is_penalized = False
            self.penalty_reason = ""
            logger.info(f"Penalty expired for {self.pubkey.hex()[:16]}...")

        return self.is_penalized

    def serialize(self) -> bytes:
        """Serialize profile for storage."""
        data = bytearray()

        # Header
        data.extend(self.pubkey)
        data.extend(struct.pack('<f', self.aggregate_score))
        data.extend(struct.pack('<Q', self.created_at))
        data.extend(struct.pack('<Q', self.last_updated))
        data.extend(struct.pack('<I', self.total_events))
        data.extend(struct.pack('<B', 1 if self.is_penalized else 0))
        data.extend(struct.pack('<Q', self.penalty_until))

        # Dimensions
        for dim in ReputationDimension:
            score = self.dimensions[dim]
            data.extend(struct.pack('<f', score.value))
            data.extend(struct.pack('<f', score.confidence))
            data.extend(struct.pack('<I', score.samples))
            data.extend(struct.pack('<Q', score.last_update))

        # Trust sets (count + pubkeys)
        data.extend(struct.pack('<H', len(self.trusted_by)))
        for pk in self.trusted_by:
            data.extend(pk)

        data.extend(struct.pack('<H', len(self.trusts)))
        for pk in self.trusts:
            data.extend(pk)

        return bytes(data)

    @classmethod
    def deserialize(cls, data: bytes) -> 'AdonisProfile':
        """Deserialize profile from bytes."""
        offset = 0

        pubkey = data[offset:offset+32]
        offset += 32

        aggregate_score = struct.unpack_from('<f', data, offset)[0]
        offset += 4

        created_at = struct.unpack_from('<Q', data, offset)[0]
        offset += 8

        last_updated = struct.unpack_from('<Q', data, offset)[0]
        offset += 8

        total_events = struct.unpack_from('<I', data, offset)[0]
        offset += 4

        is_penalized = struct.unpack_from('<B', data, offset)[0] == 1
        offset += 1

        penalty_until = struct.unpack_from('<Q', data, offset)[0]
        offset += 8

        # Dimensions
        dimensions = {}
        for dim in ReputationDimension:
            value = struct.unpack_from('<f', data, offset)[0]
            offset += 4
            confidence = struct.unpack_from('<f', data, offset)[0]
            offset += 4
            samples = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            last_update = struct.unpack_from('<Q', data, offset)[0]
            offset += 8

            dimensions[dim] = DimensionScore(
                value=value,
                confidence=confidence,
                samples=samples,
                last_update=last_update
            )

        # Trust sets
        trusted_by_count = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        trusted_by = set()
        for _ in range(trusted_by_count):
            trusted_by.add(data[offset:offset+32])
            offset += 32

        trusts_count = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        trusts = set()
        for _ in range(trusts_count):
            trusts.add(data[offset:offset+32])
            offset += 32

        return cls(
            pubkey=pubkey,
            dimensions=dimensions,
            aggregate_score=aggregate_score,
            trusted_by=trusted_by,
            trusts=trusts,
            is_penalized=is_penalized,
            penalty_until=penalty_until,
            created_at=created_at,
            last_updated=last_updated,
            total_events=total_events
        )


# ============================================================================
# ADONIS REPUTATION ENGINE
# ============================================================================

class AdonisEngine:
    """
    Main reputation engine implementing the Adonis model.

    Features:
    - Multi-dimensional reputation tracking
    - Event-based scoring updates
    - Trust graph management
    - Penalty and recovery mechanisms
    - Integration with consensus probabilities
    """

    # Event impact values (positive or negative)
    EVENT_IMPACTS = {
        ReputationEvent.BLOCK_PRODUCED: 0.05,
        ReputationEvent.BLOCK_VALIDATED: 0.02,
        ReputationEvent.TX_RELAYED: 0.01,
        ReputationEvent.UPTIME_CHECKPOINT: 0.02,  # Hourly uptime tick
        ReputationEvent.STORAGE_UPDATE: 0.01,     # Storage sync
        ReputationEvent.NEW_COUNTRY: 0.25,        # Big bonus for country diversity
        ReputationEvent.NEW_CITY: 0.15,           # Bonus for city diversity
        ReputationEvent.HANDSHAKE_FORMED: 0.10,   # Mutual trust bonus
        ReputationEvent.BLOCK_INVALID: -0.15,
        ReputationEvent.VRF_INVALID: -0.20,
        ReputationEvent.VDF_INVALID: -0.25,
        ReputationEvent.EQUIVOCATION: -1.0,       # Catastrophic
        ReputationEvent.DOWNTIME: -0.10,
        ReputationEvent.SPAM_DETECTED: -0.20,
        ReputationEvent.HANDSHAKE_BROKEN: -0.05,  # Lost trust
    }

    # Dimension affected by each event (5 fingers)
    EVENT_DIMENSIONS = {
        # TIME (Thumb) - 50%
        ReputationEvent.UPTIME_CHECKPOINT: ReputationDimension.TIME,
        ReputationEvent.DOWNTIME: ReputationDimension.TIME,
        # INTEGRITY (Index) - 20%
        ReputationEvent.BLOCK_PRODUCED: ReputationDimension.INTEGRITY,
        ReputationEvent.BLOCK_VALIDATED: ReputationDimension.INTEGRITY,
        ReputationEvent.TX_RELAYED: ReputationDimension.INTEGRITY,
        ReputationEvent.BLOCK_INVALID: ReputationDimension.INTEGRITY,
        ReputationEvent.VRF_INVALID: ReputationDimension.INTEGRITY,
        ReputationEvent.VDF_INVALID: ReputationDimension.INTEGRITY,
        ReputationEvent.EQUIVOCATION: ReputationDimension.INTEGRITY,
        ReputationEvent.SPAM_DETECTED: ReputationDimension.INTEGRITY,
        # STORAGE (Middle) - 15%
        ReputationEvent.STORAGE_UPDATE: ReputationDimension.STORAGE,
        # GEOGRAPHY (Ring) - 10% - country + city
        ReputationEvent.NEW_COUNTRY: ReputationDimension.GEOGRAPHY,
        ReputationEvent.NEW_CITY: ReputationDimension.GEOGRAPHY,
        # HANDSHAKE (Pinky) - 5% - mutual trust
        ReputationEvent.HANDSHAKE_FORMED: ReputationDimension.HANDSHAKE,
        ReputationEvent.HANDSHAKE_BROKEN: ReputationDimension.HANDSHAKE,
    }

    # Penalty durations (seconds)
    PENALTY_DURATIONS = {
        ReputationEvent.EQUIVOCATION: 180 * 86400,  # 180 days
        ReputationEvent.VDF_INVALID: 30 * 86400,    # 30 days
        ReputationEvent.VRF_INVALID: 14 * 86400,    # 14 days
        ReputationEvent.SPAM_DETECTED: 7 * 86400,   # 7 days
    }

    def __init__(self, storage=None, data_dir: str = None):
        self.profiles: Dict[bytes, AdonisProfile] = {}
        self.storage = storage
        # Default data_dir is the adonis module directory
        if data_dir is None:
            import os
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir
        self._lock = threading.RLock()

        # Rate limiting: voucher_pubkey -> list of vouch timestamps
        self._vouch_history: Dict[bytes, List[int]] = defaultdict(list)

        # Current block height for timestamp validation
        self._current_height: int = 0

        # Configuration - The Five Fingers of Adonis (sum = 100%)
        # TIME is the THUMB - the main factor (50%) - this is Proof of TIME
        self.dimension_weights = {
            ReputationDimension.TIME: 0.50,        # THUMB: Continuous uptime
            ReputationDimension.INTEGRITY: 0.20,   # INDEX: No violations
            ReputationDimension.STORAGE: 0.15,     # MIDDLE: Chain storage
            ReputationDimension.GEOGRAPHY: 0.10,   # RING: Country + city
            ReputationDimension.HANDSHAKE: 0.05,   # PINKY: Mutual trust
        }

        # Saturation thresholds
        self.K_TIME = 15_552_000    # 180 days in seconds
        self.K_STORAGE = 1.00       # 100% of chain
        self.K_HANDSHAKE = 10       # 10 handshakes for full score

        # Minimum requirements for handshake eligibility
        self.HANDSHAKE_MIN_TIME = 0.9       # 90% of TIME saturation (~162 days)
        self.HANDSHAKE_MIN_INTEGRITY = 0.8  # 80% INTEGRITY
        self.HANDSHAKE_MIN_STORAGE = 0.9    # 90% STORAGE
        self.HANDSHAKE_MIN_GEOGRAPHY = 0.1  # Must have registered location

        # Country tracking for global decentralization
        # Maps country_code -> set of node pubkeys in that country
        self._country_nodes: Dict[str, Set[bytes]] = defaultdict(set)

        # City hash tracking for geographic diversity
        # Maps city_hash -> set of node pubkeys in that city
        self._city_nodes: Dict[bytes, Set[bytes]] = defaultdict(set)

        # Handshake tracking
        # Maps handshake_id -> Handshake
        self._handshakes: Dict[bytes, Handshake] = {}

        # Load persisted state
        self._load_from_file()

        logger.info("Adonis Reputation Engine initialized (5 Fingers model)")

    def set_current_height(self, height: int):
        """Update current block height for timestamp validation."""
        self._current_height = height

    def get_or_create_profile(self, pubkey: bytes) -> AdonisProfile:
        """Get existing profile or create new one."""
        with self._lock:
            if pubkey not in self.profiles:
                self.profiles[pubkey] = AdonisProfile(pubkey=pubkey)
                logger.debug(f"Created new Adonis profile for {pubkey.hex()[:16]}...")
            return self.profiles[pubkey]

    def record_event(
        self,
        pubkey: bytes,
        event_type: ReputationEvent,
        height: int = 0,
        source: Optional[bytes] = None,
        evidence: Optional[bytes] = None,
        timestamp: Optional[int] = None
    ) -> float:
        """
        Record a reputation event and update scores.

        Args:
            pubkey: Node public key
            event_type: Type of reputation event
            height: Block height when event occurred (for validation)
            source: Source node for peer events
            evidence: Hash of evidence
            timestamp: Event timestamp (validated against current time)

        Returns:
            New aggregate score after event, or -1 if validation failed
        """
        with self._lock:
            profile = self.get_or_create_profile(pubkey)
            current_time = int(time.time())

            # Timestamp validation (ADN-M3 fix)
            if timestamp is not None:
                # Reject future timestamps (with small drift allowance)
                if timestamp > current_time + MAX_TIMESTAMP_DRIFT:
                    logger.warning(
                        f"Rejected event with future timestamp: {timestamp} > {current_time}"
                    )
                    return -1.0

                # Reject very old timestamps (older than 24h)
                if timestamp < current_time - 86400:
                    logger.warning(
                        f"Rejected event with stale timestamp: {timestamp}"
                    )
                    return -1.0

                current_time = timestamp

            # Height validation
            if height > 0 and self._current_height > 0:
                # Height should not be far in future
                if height > self._current_height + 10:
                    logger.warning(
                        f"Rejected event with future height: {height} > {self._current_height}"
                    )
                    return -1.0

            # Get impact and dimension
            impact = self.EVENT_IMPACTS.get(event_type, 0.0)
            dimension = self.EVENT_DIMENSIONS.get(event_type)

            # Create record
            record = ReputationRecord(
                event_type=event_type,
                timestamp=current_time,
                impact=impact,
                height=height,
                source=source,
                evidence=evidence
            )

            profile.add_event(record)

            # Update dimension score
            if dimension:
                # Convert impact to observation [0, 1]
                if impact >= 0:
                    observation = 0.5 + impact * 0.5  # Positive: 0.5-1.0
                else:
                    observation = 0.5 + impact * 0.5  # Negative: 0.0-0.5
                observation = max(0.0, min(1.0, observation))

                profile.dimensions[dimension].update(
                    observation,
                    weight=abs(impact) * 10,
                    timestamp=current_time
                )

            # Apply penalty if warranted
            if event_type in self.PENALTY_DURATIONS:
                duration = self.PENALTY_DURATIONS[event_type]
                profile.apply_penalty(duration, event_type.name)

            # Recompute aggregate
            new_score = profile.compute_aggregate(self.dimension_weights)

            logger.debug(
                f"Adonis event: {event_type.name} for {pubkey.hex()[:16]}... "
                f"(impact: {impact:+.2f}, new score: {new_score:.3f})"
            )

            return new_score

    def add_vouch(self, voucher: bytes, vouchee: bytes) -> bool:
        """
        Add a trust vouch from voucher to vouchee.

        Rate limited to MAX_VOUCHES_PER_DAY per voucher.

        Returns:
            True if vouch was added, False if rate limited or already exists
        """
        with self._lock:
            current_time = int(time.time())

            # Self-vouch protection
            if voucher == vouchee:
                logger.warning(f"Self-vouch rejected for {voucher.hex()[:16]}...")
                return False

            # Rate limiting (ADN-L1 fix)
            day_ago = current_time - 86400
            recent_vouches = [
                t for t in self._vouch_history[voucher]
                if t > day_ago
            ]
            self._vouch_history[voucher] = recent_vouches

            if len(recent_vouches) >= MAX_VOUCHES_PER_DAY:
                logger.warning(
                    f"Vouch rate limit exceeded for {voucher.hex()[:16]}... "
                    f"({len(recent_vouches)}/{MAX_VOUCHES_PER_DAY} per day)"
                )
                return False

            voucher_profile = self.get_or_create_profile(voucher)
            vouchee_profile = self.get_or_create_profile(vouchee)

            if vouchee in voucher_profile.trusts:
                return False  # Already vouching

            voucher_profile.trusts.add(vouchee)
            vouchee_profile.trusted_by.add(voucher)
            self._vouch_history[voucher].append(current_time)

            # Note: One-way vouches are tracked but don't affect Adonis score
            # Mutual trust requires HANDSHAKE (two-way, both nodes saturated)

            logger.info(
                f"Trust vouch: {voucher.hex()[:16]}... -> {vouchee.hex()[:16]}..."
            )

            # Auto-save after vouch
            self._save_to_file()

            return True

    def remove_vouch(self, voucher: bytes, vouchee: bytes) -> bool:
        """Remove a trust vouch."""
        with self._lock:
            if voucher not in self.profiles or vouchee not in self.profiles:
                return False

            voucher_profile = self.profiles[voucher]
            vouchee_profile = self.profiles[vouchee]

            voucher_profile.trusts.discard(vouchee)
            vouchee_profile.trusted_by.discard(voucher)

            return True

    # =========================================================================
    # TIME AND STORAGE UPDATES
    # =========================================================================

    def update_time(self, pubkey: bytes, uptime_seconds: int) -> float:
        """
        Update TIME dimension based on continuous uptime.

        Args:
            pubkey: Node public key
            uptime_seconds: Continuous uptime in seconds

        Returns:
            TIME score in [0, 1]
        """
        with self._lock:
            profile = self.get_or_create_profile(pubkey)

            # Saturating function: max at K_TIME (180 days)
            time_score = min(uptime_seconds / self.K_TIME, 1.0)

            profile.dimensions[ReputationDimension.TIME].update(
                time_score,
                weight=2.0,  # High weight for stability
                timestamp=int(time.time())
            )

            # Record uptime checkpoint event
            self.record_event(pubkey, ReputationEvent.UPTIME_CHECKPOINT)

            logger.debug(
                f"Node {pubkey.hex()[:16]}... TIME updated: "
                f"{uptime_seconds/86400:.1f} days = {time_score:.3f}"
            )

            return time_score

    def update_storage(
        self,
        pubkey: bytes,
        stored_blocks: int,
        total_blocks: int
    ) -> float:
        """
        Update STORAGE dimension based on chain storage.

        Args:
            pubkey: Node public key
            stored_blocks: Number of blocks stored
            total_blocks: Total blocks in chain

        Returns:
            STORAGE score in [0, 1]
        """
        with self._lock:
            if total_blocks == 0:
                return 0.0

            profile = self.get_or_create_profile(pubkey)

            # Storage ratio
            storage_ratio = stored_blocks / total_blocks

            # Saturating at K_STORAGE (80%)
            storage_score = min(storage_ratio / self.K_STORAGE, 1.0)

            profile.dimensions[ReputationDimension.STORAGE].update(
                storage_score,
                weight=1.0,
                timestamp=int(time.time())
            )

            logger.debug(
                f"Node {pubkey.hex()[:16]}... STORAGE updated: "
                f"{stored_blocks}/{total_blocks} ({storage_ratio*100:.1f}%) = {storage_score:.3f}"
            )

            return storage_score

    def compute_node_probability(
        self,
        pubkey: bytes,
        uptime_seconds: int,
        stored_blocks: int,
        total_blocks: int
    ) -> float:
        """
        Compute complete node probability using unified Adonis formula.

        This is the ONLY formula for node weight. No separate f_time/f_space/f_rep.

        Args:
            pubkey: Node public key
            uptime_seconds: Continuous uptime
            stored_blocks: Blocks stored
            total_blocks: Total chain blocks

        Returns:
            Adonis score in [0, 1] (unnormalized probability)
        """
        with self._lock:
            profile = self.get_or_create_profile(pubkey)
            current_time = int(time.time())

            # Update TIME
            time_score = min(uptime_seconds / self.K_TIME, 1.0)
            profile.dimensions[ReputationDimension.TIME].value = time_score
            profile.dimensions[ReputationDimension.TIME].confidence = min(
                1.0, uptime_seconds / (7 * 86400)  # Full confidence after 7 days
            )

            # Update STORAGE
            if total_blocks > 0:
                storage_ratio = stored_blocks / total_blocks
                storage_score = min(storage_ratio / self.K_STORAGE, 1.0)
                profile.dimensions[ReputationDimension.STORAGE].value = storage_score
                profile.dimensions[ReputationDimension.STORAGE].confidence = 1.0

            # Compute aggregate with all 7 dimensions
            score = profile.compute_aggregate(self.dimension_weights)

            # Apply penalty if active
            if profile.check_penalty(current_time):
                score *= 0.1  # 90% reduction

            return score

    def get_reputation_score(self, pubkey: bytes) -> float:
        """
        Get node's reputation score for consensus.

        Returns value in [0, 1] suitable for probability calculation.
        """
        with self._lock:
            if pubkey not in self.profiles:
                return 0.0

            profile = self.profiles[pubkey]
            current_time = int(time.time())

            # Check penalty
            if profile.check_penalty(current_time):
                return 0.1 * profile.aggregate_score  # 90% reduction

            return profile.aggregate_score

    def get_reputation_multiplier(self, pubkey: bytes) -> float:
        """
        Get reputation multiplier for consensus probability.

        Returns value that modifies base probability:
        - 1.0 = neutral (no effect)
        - >1.0 = bonus (good reputation)
        - <1.0 = penalty (bad reputation)

        Range: [0.1, 2.0]
        """
        score = self.get_reputation_score(pubkey)

        # Map [0, 1] to [0.1, 2.0]
        # Score 0.5 = multiplier 1.0 (neutral)
        # Score 1.0 = multiplier 2.0 (maximum bonus)
        # Score 0.0 = multiplier 0.1 (maximum penalty)

        return 0.1 + score * 1.9

    def get_profile(self, pubkey: bytes) -> Optional[AdonisProfile]:
        """Get profile for a node."""
        return self.profiles.get(pubkey)

    def get_top_nodes(self, limit: int = 100) -> List[Tuple[bytes, float]]:
        """Get top nodes by reputation score."""
        with self._lock:
            scored = [
                (pk, profile.aggregate_score)
                for pk, profile in self.profiles.items()
                if not profile.is_penalized
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:limit]

    def get_trust_graph(self) -> Dict[bytes, Set[bytes]]:
        """Get the complete trust graph."""
        with self._lock:
            return {
                pk: profile.trusts.copy()
                for pk, profile in self.profiles.items()
            }

    def compute_pagerank(self, damping: float = 0.85, iterations: int = 20) -> Dict[bytes, float]:
        """
        Compute PageRank-style trust scores from the trust graph.

        Nodes vouched by high-trust nodes get higher scores.
        """
        with self._lock:
            if not self.profiles:
                return {}

            # Initialize scores
            n = len(self.profiles)
            scores = {pk: 1.0 / n for pk in self.profiles}

            for _ in range(iterations):
                new_scores = {}

                for pk in self.profiles:
                    # Sum of incoming trust weighted by source scores
                    incoming = sum(
                        scores[src] / max(1, len(self.profiles[src].trusts))
                        for src in self.profiles[pk].trusted_by
                        if src in scores
                    )

                    new_scores[pk] = (1 - damping) / n + damping * incoming

                # Normalize
                total = sum(new_scores.values())
                if total > 0:
                    scores = {pk: s / total for pk, s in new_scores.items()}

            return scores

    def get_stats(self) -> Dict[str, Any]:
        """Get Adonis engine statistics."""
        with self._lock:
            active = [p for p in self.profiles.values() if not p.is_penalized]
            penalized = [p for p in self.profiles.values() if p.is_penalized]

            total_vouches = sum(len(p.trusts) for p in self.profiles.values())
            avg_score = (
                sum(p.aggregate_score for p in active) / len(active)
                if active else 0.0
            )

            return {
                'total_profiles': len(self.profiles),
                'active_profiles': len(active),
                'penalized_profiles': len(penalized),
                'total_vouches': total_vouches,
                'average_score': avg_score,
                'unique_countries': len(self._country_nodes),
                'unique_cities': len(self._city_nodes),
                'dimension_weights': {
                    dim.name: weight
                    for dim, weight in self.dimension_weights.items()
                }
            }

    # =========================================================================
    # GEOGRAPHIC DIVERSITY
    # =========================================================================

    def compute_city_hash(self, country: str, city: str) -> bytes:
        """
        Compute anonymous city hash from location.

        Privacy: Only stores hash, not raw location data.
        The hash is deterministic so nodes in same city have same hash.

        Args:
            country: Country code (e.g., "US", "DE", "JP")
            city: City name (case-insensitive)

        Returns:
            32-byte SHA256 hash of normalized location
        """
        # Normalize: lowercase, strip whitespace
        normalized = f"{country.upper().strip()}:{city.lower().strip()}"
        return sha256(normalized.encode('utf-8'))

    def register_node_location(
        self,
        pubkey: bytes,
        country: str,
        city: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, bool, float, float]:
        """
        Register node's geographic location anonymously.

        Privacy guarantees:
        - IP address is NEVER stored
        - Only country_code and city_hash are stored
        - Cannot reverse-engineer city from hash

        Args:
            pubkey: Node public key
            country: Country code (e.g., "US", "DE", "JP")
            city: City name
            ip_address: Optional IP (used only for geolocation, not stored)

        Returns:
            Tuple of (is_new_country, is_new_city, country_score, city_score)
            is_new_country: True if this is first node from this country
            is_new_city: True if this is first node from this city
            country_score: Updated country dimension score
            city_score: Updated geography dimension score
        """
        with self._lock:
            profile = self.get_or_create_profile(pubkey)
            country_code = country.upper().strip()
            city_hash = self.compute_city_hash(country, city)

            # === COUNTRY TRACKING ===
            # Check if this is a new country for the network
            is_new_country = len(self._country_nodes[country_code]) == 0

            # Update profile's country
            old_country = profile.country_code
            if old_country and old_country != country_code:
                # Node moved countries - remove from old country
                self._country_nodes[old_country].discard(pubkey)
                if not self._country_nodes[old_country]:
                    del self._country_nodes[old_country]

            profile.country_code = country_code
            self._country_nodes[country_code].add(pubkey)

            # Calculate country diversity score
            # Fewer nodes in country = higher score (encourages global decentralization)
            nodes_in_country = len(self._country_nodes[country_code])
            total_countries = len(self._country_nodes)

            # Score based on country rarity (stronger than city)
            # 1 node = 1.0, 10 nodes = 0.5, 100 nodes = 0.25
            country_rarity = 1.0 / (1.0 + math.log10(nodes_in_country))

            # Big bonus for network having many countries
            country_diversity = min(1.0, total_countries / 50)  # Max at 50 countries

            country_score = 0.6 * country_rarity + 0.4 * country_diversity

            # Update GEOGRAPHY dimension (RING) - country contributes to geography
            # Note: We update the same GEOGRAPHY dimension for both country and city
            # The combined score reflects overall geographic diversity

            # Award NEW_COUNTRY event if first node from this country
            if is_new_country:
                self.record_event(pubkey, ReputationEvent.NEW_COUNTRY)
                logger.info(
                    f"NEW COUNTRY! Node {pubkey.hex()[:16]}... "
                    f"is first from {country_code} (total countries: {total_countries})"
                )

            # === CITY TRACKING ===
            # Check if this is a new city for the network
            is_new_city = len(self._city_nodes[city_hash]) == 0

            # Update profile's city hash
            old_city_hash = profile.city_hash
            if old_city_hash and old_city_hash != city_hash:
                # Node moved cities - remove from old city
                self._city_nodes[old_city_hash].discard(pubkey)
                if not self._city_nodes[old_city_hash]:
                    del self._city_nodes[old_city_hash]

            profile.city_hash = city_hash
            self._city_nodes[city_hash].add(pubkey)

            # Calculate city diversity score
            nodes_in_city = len(self._city_nodes[city_hash])
            total_cities = len(self._city_nodes)

            city_rarity = 1.0 / (1.0 + math.log10(nodes_in_city))
            city_diversity = min(1.0, total_cities / 100)  # Max at 100 cities

            city_score = 0.7 * city_rarity + 0.3 * city_diversity

            # Combined GEOGRAPHY score (RING finger):
            # 60% country contribution, 40% city contribution
            geography_score = 0.6 * country_score + 0.4 * city_score

            # Update GEOGRAPHY dimension (RING)
            profile.dimensions[ReputationDimension.GEOGRAPHY].update(
                geography_score,
                weight=1.5,
                timestamp=int(time.time())
            )

            # Award NEW_CITY event if first node from this city
            if is_new_city:
                self.record_event(pubkey, ReputationEvent.NEW_CITY)
                logger.info(
                    f"New city! Node {pubkey.hex()[:16]}... "
                    f"is first from city hash {city_hash.hex()[:16]}..."
                )

            logger.debug(
                f"Node {pubkey.hex()[:16]}... registered: "
                f"country={country_code} (score={country_score:.3f}, nodes={nodes_in_country}), "
                f"city={city_hash.hex()[:8]}... (score={city_score:.3f}, nodes={nodes_in_city})"
            )

            return is_new_country, is_new_city, country_score, city_score

    def get_country_distribution(self) -> Dict[str, int]:
        """
        Get distribution of nodes per country.

        Returns dict mapping country_code -> node_count.
        """
        with self._lock:
            return {
                country: len(nodes)
                for country, nodes in self._country_nodes.items()
            }

    def get_city_distribution(self) -> Dict[str, int]:
        """
        Get distribution of nodes per city (anonymized).

        Returns dict mapping city_hash_prefix -> node_count.
        Only returns first 8 chars of hash for additional privacy.
        """
        with self._lock:
            return {
                city_hash.hex()[:8]: len(nodes)
                for city_hash, nodes in self._city_nodes.items()
            }

    def get_geographic_diversity_score(self) -> float:
        """
        Calculate overall network geographic diversity.

        Higher score = more decentralized geographically.
        Uses Gini coefficient inversion.

        Returns:
            Score in [0, 1] where 1 = perfectly distributed
        """
        with self._lock:
            if not self._city_nodes:
                return 0.0

            counts = sorted([len(nodes) for nodes in self._city_nodes.values()])
            n = len(counts)
            total = sum(counts)

            if total == 0 or n == 0:
                return 0.0

            # Gini coefficient calculation
            cumulative = 0
            for i, count in enumerate(counts):
                cumulative += (2 * (i + 1) - n - 1) * count

            gini = cumulative / (n * total)

            # Invert: high Gini = unequal, we want low Gini = high score
            return 1.0 - gini

    def update_node_location_from_ip(
        self,
        pubkey: bytes,
        ip_address: str
    ) -> Optional[Tuple[bool, bool, float, float]]:
        """
        Update node location from IP address using free geolocation.

        Privacy: IP is used only for lookup, never stored.

        Args:
            pubkey: Node public key
            ip_address: Node's IP address

        Returns:
            Tuple of (is_new_country, is_new_city, country_score, city_score)
            or None if geolocation failed
        """
        try:
            # Try to use ip-api.com (free, no key required)
            import urllib.request
            import json

            # Skip private IPs
            if ip_address.startswith(('10.', '192.168.', '172.', '127.', 'localhost')):
                logger.debug(f"Skipping private IP: {ip_address}")
                return None

            url = f"http://ip-api.com/json/{ip_address}?fields=status,country,city,countryCode"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())

            if data.get('status') != 'success':
                logger.debug(f"Geolocation failed for {ip_address}")
                return None

            country = data.get('countryCode', 'XX')
            city = data.get('city', 'Unknown')

            # Register location (IP is NOT passed to storage)
            return self.register_node_location(pubkey, country, city)

        except Exception as e:
            logger.debug(f"Geolocation error for {ip_address}: {e}")
            return None

    # =========================================================================
    # HANDSHAKE - PINKY FINGER (5%)
    # =========================================================================

    def is_eligible_for_handshake(self, pubkey: bytes) -> Tuple[bool, str]:
        """
        Check if a node is eligible to form handshakes.

        Requires all 4 fingers to be near saturation:
        - TIME >= 90% (162+ days)
        - INTEGRITY >= 80%
        - STORAGE >= 90%
        - GEOGRAPHY > 10% (registered location)

        Returns:
            Tuple of (eligible, reason)
        """
        with self._lock:
            if pubkey not in self.profiles:
                return False, "Profile not found"

            profile = self.profiles[pubkey]

            # Check penalty
            if profile.is_penalized:
                return False, "Node is penalized"

            # Check TIME (THUMB)
            time_score = profile.dimensions[ReputationDimension.TIME].value
            if time_score < self.HANDSHAKE_MIN_TIME:
                return False, f"TIME too low: {time_score:.2f} < {self.HANDSHAKE_MIN_TIME}"

            # Check INTEGRITY (INDEX)
            integrity_score = profile.dimensions[ReputationDimension.INTEGRITY].value
            if integrity_score < self.HANDSHAKE_MIN_INTEGRITY:
                return False, f"INTEGRITY too low: {integrity_score:.2f} < {self.HANDSHAKE_MIN_INTEGRITY}"

            # Check STORAGE (MIDDLE)
            storage_score = profile.dimensions[ReputationDimension.STORAGE].value
            if storage_score < self.HANDSHAKE_MIN_STORAGE:
                return False, f"STORAGE too low: {storage_score:.2f} < {self.HANDSHAKE_MIN_STORAGE}"

            # Check GEOGRAPHY (RING)
            geography_score = profile.dimensions[ReputationDimension.GEOGRAPHY].value
            if geography_score < self.HANDSHAKE_MIN_GEOGRAPHY:
                return False, f"GEOGRAPHY too low: {geography_score:.2f} (register location first)"

            return True, "Eligible for handshake"

    def request_handshake(
        self,
        requester: bytes,
        target: bytes
    ) -> Tuple[bool, str]:
        """
        Request a handshake with another node.

        Both nodes must be eligible (4 fingers saturated).
        Nodes must be in DIFFERENT countries (anti-sybil).

        Returns:
            Tuple of (success, message)
        """
        with self._lock:
            # Check self-handshake
            if requester == target:
                return False, "Cannot handshake with yourself"

            # Check if handshake already exists
            handshake_id = sha256(min(requester, target) + max(requester, target))
            if handshake_id in self._handshakes:
                return False, "Handshake already exists"

            # Check requester eligibility
            eligible, reason = self.is_eligible_for_handshake(requester)
            if not eligible:
                return False, f"Requester not eligible: {reason}"

            # Check target eligibility
            eligible, reason = self.is_eligible_for_handshake(target)
            if not eligible:
                return False, f"Target not eligible: {reason}"

            # Check different countries (anti-sybil)
            requester_profile = self.profiles[requester]
            target_profile = self.profiles[target]

            if requester_profile.country_code == target_profile.country_code:
                return False, f"Same country ({requester_profile.country_code}) - handshakes require different countries"

            return True, "Ready for handshake"

    def form_handshake(
        self,
        node_a: bytes,
        node_b: bytes,
        sig_a: bytes,
        sig_b: bytes,
        height: int
    ) -> Tuple[bool, str]:
        """
        Form a mutual handshake between two veteran nodes.

        This is called when both nodes have agreed to shake hands.

        Returns:
            Tuple of (success, message)
        """
        with self._lock:
            # Validate request first
            success, reason = self.request_handshake(node_a, node_b)
            if not success:
                return False, reason

            # Create handshake
            handshake = Handshake(
                node_a=node_a,
                node_b=node_b,
                created_at=height,
                sig_a=sig_a,
                sig_b=sig_b
            )

            # Store handshake
            self._handshakes[handshake.get_id()] = handshake

            # Update profiles
            profile_a = self.profiles[node_a]
            profile_b = self.profiles[node_b]

            profile_a.handshake_partners.add(node_b)
            profile_b.handshake_partners.add(node_a)

            # Record events and update HANDSHAKE dimension
            self.record_event(node_a, ReputationEvent.HANDSHAKE_FORMED, height=height, source=node_b)
            self.record_event(node_b, ReputationEvent.HANDSHAKE_FORMED, height=height, source=node_a)

            # Update handshake scores
            self._update_handshake_score(node_a)
            self._update_handshake_score(node_b)

            logger.info(
                f"🤝 HANDSHAKE formed: {node_a.hex()[:8]}... ({profile_a.country_code}) <-> "
                f"{node_b.hex()[:8]}... ({profile_b.country_code})"
            )

            return True, "Handshake formed successfully"

    def break_handshake(
        self,
        node_a: bytes,
        node_b: bytes,
        reason: str = "manual"
    ) -> Tuple[bool, str]:
        """
        Break an existing handshake.

        Called when:
        - One node is penalized (equivocation)
        - One node goes offline for extended period
        - Manual break request

        Returns:
            Tuple of (success, message)
        """
        with self._lock:
            handshake_id = sha256(min(node_a, node_b) + max(node_a, node_b))

            if handshake_id not in self._handshakes:
                return False, "Handshake not found"

            # Remove handshake
            del self._handshakes[handshake_id]

            # Update profiles
            if node_a in self.profiles:
                self.profiles[node_a].handshake_partners.discard(node_b)
                self.record_event(node_a, ReputationEvent.HANDSHAKE_BROKEN, source=node_b)
                self._update_handshake_score(node_a)

            if node_b in self.profiles:
                self.profiles[node_b].handshake_partners.discard(node_a)
                self.record_event(node_b, ReputationEvent.HANDSHAKE_BROKEN, source=node_a)
                self._update_handshake_score(node_b)

            logger.info(f"Handshake broken: {node_a.hex()[:8]}... <-> {node_b.hex()[:8]}... (reason: {reason})")

            return True, "Handshake broken"

    def _update_handshake_score(self, pubkey: bytes):
        """Update the HANDSHAKE dimension score based on active handshakes."""
        if pubkey not in self.profiles:
            return

        profile = self.profiles[pubkey]
        handshake_count = len(profile.handshake_partners)

        # Score saturates at K_HANDSHAKE (10)
        handshake_score = min(1.0, handshake_count / self.K_HANDSHAKE)

        profile.dimensions[ReputationDimension.HANDSHAKE].value = handshake_score
        profile.dimensions[ReputationDimension.HANDSHAKE].confidence = 1.0
        profile.dimensions[ReputationDimension.HANDSHAKE].last_update = int(time.time())

    def get_handshakes(self, pubkey: bytes) -> List[Handshake]:
        """Get all active handshakes for a node."""
        with self._lock:
            return [h for h in self._handshakes.values() if h.involves(pubkey)]

    def get_handshake_count(self, pubkey: bytes) -> int:
        """Get count of active handshakes for a node."""
        with self._lock:
            if pubkey not in self.profiles:
                return 0
            return len(self.profiles[pubkey].handshake_partners)

    def get_trust_web_stats(self) -> Dict[str, Any]:
        """Get statistics about the trust web (all handshakes)."""
        with self._lock:
            total_handshakes = len(self._handshakes)
            nodes_with_handshakes = set()

            for handshake in self._handshakes.values():
                nodes_with_handshakes.add(handshake.node_a)
                nodes_with_handshakes.add(handshake.node_b)

            # Country pairs
            country_pairs = defaultdict(int)
            for handshake in self._handshakes.values():
                if handshake.node_a in self.profiles and handshake.node_b in self.profiles:
                    c1 = self.profiles[handshake.node_a].country_code or "XX"
                    c2 = self.profiles[handshake.node_b].country_code or "XX"
                    pair = tuple(sorted([c1, c2]))
                    country_pairs[pair] += 1

            return {
                'total_handshakes': total_handshakes,
                'nodes_with_handshakes': len(nodes_with_handshakes),
                'eligible_nodes': sum(
                    1 for pk in self.profiles
                    if self.is_eligible_for_handshake(pk)[0]
                ),
                'country_pairs': dict(country_pairs),
            }

    def save_state(self):
        """Save engine state to storage."""
        if self.storage is None:
            return

        with self._lock:
            for pubkey, profile in self.profiles.items():
                data = profile.serialize()
                self.storage.store_adonis_profile(pubkey, data)

    def load_state(self):
        """Load engine state from storage."""
        if self.storage is None:
            return

        with self._lock:
            profiles_data = self.storage.load_adonis_profiles()
            for pubkey, data in profiles_data.items():
                self.profiles[pubkey] = AdonisProfile.deserialize(data)

            logger.info(f"Loaded {len(self.profiles)} Adonis profiles")

    # =========================================================================
    # PERSISTENCE (ADN-M1 fix)
    # =========================================================================

    def _get_state_file(self) -> str:
        """Get path to state file."""
        import os
        return os.path.join(self.data_dir, "adonis_state.bin")

    def _save_to_file(self):
        """Save profiles to file for persistence."""
        import os
        try:
            state_file = self._get_state_file()

            # Ensure directory exists
            os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)

            with open(state_file, 'wb') as f:
                # Write version
                f.write(struct.pack('<H', 1))  # Version 1

                # Write profile count
                f.write(struct.pack('<I', len(self.profiles)))

                # Write each profile
                for pubkey, profile in self.profiles.items():
                    data = profile.serialize()
                    f.write(struct.pack('<I', len(data)))
                    f.write(data)

            logger.debug(f"Saved {len(self.profiles)} Adonis profiles to {state_file}")

        except Exception as e:
            logger.error(f"Failed to save Adonis state: {e}")

    def _load_from_file(self):
        """Load profiles from file."""
        import os
        state_file = self._get_state_file()

        if not os.path.exists(state_file):
            logger.debug("No Adonis state file found, starting fresh")
            return

        try:
            with open(state_file, 'rb') as f:
                # Read version
                version = struct.unpack('<H', f.read(2))[0]
                if version != 1:
                    logger.warning(f"Unknown Adonis state version: {version}")
                    return

                # Read profile count
                count = struct.unpack('<I', f.read(4))[0]

                # Read profiles
                for _ in range(count):
                    data_len = struct.unpack('<I', f.read(4))[0]
                    data = f.read(data_len)
                    profile = AdonisProfile.deserialize(data)
                    self.profiles[profile.pubkey] = profile

            logger.info(f"Loaded {len(self.profiles)} Adonis profiles from {state_file}")

        except Exception as e:
            logger.error(f"Failed to load Adonis state: {e}")

    # =========================================================================
    # GARBAGE COLLECTION
    # =========================================================================

    def garbage_collect(self, force: bool = False) -> int:
        """
        Remove expired profiles (no activity for PROFILE_EXPIRATION_SECONDS).

        Args:
            force: If True, run even if recently run

        Returns:
            Number of profiles removed
        """
        with self._lock:
            current_time = int(time.time())
            expired = []

            for pubkey, profile in self.profiles.items():
                # Check if profile is expired
                if profile.last_updated > 0:
                    age = current_time - profile.last_updated
                else:
                    age = current_time - profile.created_at

                if age > PROFILE_EXPIRATION_SECONDS:
                    # Don't GC penalized profiles (keep for accountability)
                    if not profile.is_penalized:
                        expired.append(pubkey)

            # Remove expired profiles
            for pubkey in expired:
                # Clean up trust references
                profile = self.profiles[pubkey]
                for trusted in profile.trusts:
                    if trusted in self.profiles:
                        self.profiles[trusted].trusted_by.discard(pubkey)

                for truster in profile.trusted_by:
                    if truster in self.profiles:
                        self.profiles[truster].trusts.discard(pubkey)

                del self.profiles[pubkey]

            if expired:
                logger.info(f"Garbage collected {len(expired)} expired Adonis profiles")
                self._save_to_file()

            return len(expired)

    def periodic_maintenance(self):
        """Run periodic maintenance tasks."""
        # Garbage collect
        self.garbage_collect()

        # Save state
        self._save_to_file()


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def compute_f_rep_adonis(
    adonis_engine: AdonisEngine,
    pubkey: bytes,
    signed_blocks: int
) -> float:
    """
    Compute reputation component using Adonis model.

    This replaces the simple signed_blocks / K_REP calculation
    with the multi-dimensional Adonis score.

    Args:
        adonis_engine: Adonis engine instance
        pubkey: Node public key
        signed_blocks: Number of signed blocks (for backward compatibility)

    Returns:
        Reputation factor in [0, 1]
    """
    # Get Adonis score
    adonis_score = adonis_engine.get_reputation_score(pubkey)

    # Also consider signed blocks (for backward compatibility)
    blocks_score = min(signed_blocks / PROTOCOL.K_REP, 1.0)

    # Combine with Adonis having higher weight
    return 0.7 * adonis_score + 0.3 * blocks_score


def create_reputation_modifier(adonis_engine: AdonisEngine):
    """
    Create a probability modifier function for consensus.

    Returns a function that modifies base probability based on Adonis scores.
    """
    def modifier(pubkey: bytes, base_probability: float) -> float:
        multiplier = adonis_engine.get_reputation_multiplier(pubkey)
        return base_probability * multiplier

    return modifier


# ============================================================================
# SELF-TEST
# ============================================================================

def _self_test():
    """Run Adonis self-tests."""
    logger.info("Running Adonis self-tests...")
    logger.info("  🖐️ The Five Fingers of Adonis:")
    logger.info("     👍 THUMB (TIME): 50% - saturates at 180 days")
    logger.info("     ☝️ INDEX (INTEGRITY): 20% - no violations")
    logger.info("     🖕 MIDDLE (STORAGE): 15% - saturates at 100%")
    logger.info("     💍 RING (GEOGRAPHY): 10% - country + city")
    logger.info("     🤙 PINKY (HANDSHAKE): 5% - mutual trust")

    # Create engine
    engine = AdonisEngine()

    # Create test nodes
    node1 = b'\x01' * 32
    node2 = b'\x02' * 32
    node3 = b'\x03' * 32

    # Test profile creation
    profile1 = engine.get_or_create_profile(node1)
    assert profile1.pubkey == node1
    logger.info("  Profile creation OK")

    # Test TIME dimension (THUMB - 50%)
    time_score = engine.update_time(node1, 90 * 86400)  # 90 days
    assert time_score == 0.5  # 90/180 = 0.5
    logger.info(f"  THUMB (TIME): 90 days = {time_score:.3f}")

    time_score_full = engine.update_time(node3, 200 * 86400)  # 200 days (saturated)
    assert time_score_full == 1.0
    logger.info(f"  THUMB (TIME): 200 days (saturated) = {time_score_full:.3f}")

    # Test STORAGE dimension (MIDDLE - 15%)
    storage_score = engine.update_storage(node1, 1000, 1000)  # 100% storage
    assert storage_score == 1.0  # 100%/100% = 1.0 (saturated)
    logger.info(f"  MIDDLE (STORAGE): 100% = {storage_score:.3f}")

    storage_score_half = engine.update_storage(node3, 500, 1000)  # 50% storage
    assert storage_score_half == 0.5  # 50%/100% = 0.5
    logger.info(f"  MIDDLE (STORAGE): 50% = {storage_score_half:.3f}")

    # Test INTEGRITY (INDEX - 20%) - positive events
    for _ in range(10):
        engine.record_event(node1, ReputationEvent.BLOCK_PRODUCED, height=100)

    score1 = engine.get_reputation_score(node1)
    assert score1 > 0
    logger.info(f"  INDEX (INTEGRITY): 10 blocks = score {score1:.3f}")

    # Test INTEGRITY (INDEX - negative events)
    engine.record_event(node2, ReputationEvent.BLOCK_INVALID, height=100)
    score2 = engine.get_reputation_score(node2)
    logger.info(f"  INDEX (INTEGRITY): invalid block = score {score2:.3f}")

    # Test penalty (EQUIVOCATION)
    engine.record_event(node2, ReputationEvent.EQUIVOCATION, height=100)
    profile2 = engine.get_profile(node2)
    assert profile2.is_penalized
    logger.info("  Penalty: EQUIVOCATION applied")

    # Test unified probability calculation
    prob = engine.compute_node_probability(
        node1,
        uptime_seconds=90 * 86400,  # 90 days
        stored_blocks=800,
        total_blocks=1000
    )
    assert prob > 0
    logger.info(f"  Unified probability: {prob:.3f}")

    # Test multiplier
    mult1 = engine.get_reputation_multiplier(node1)
    mult2 = engine.get_reputation_multiplier(node2)
    assert mult1 > mult2  # Good node has higher multiplier
    logger.info(f"  Multipliers: node1={mult1:.2f}, node2={mult2:.2f}")

    # Test top nodes
    top = engine.get_top_nodes(10)
    assert len(top) >= 1
    logger.info(f"  Top nodes: {len(top)}")

    # Test stats
    stats = engine.get_stats()
    assert 'total_profiles' in stats
    logger.info("  Statistics OK")

    # =========================================================================
    # Test GEOGRAPHY dimension (RING - 10%) - country + city combined
    # =========================================================================
    node4 = b'\x04' * 32
    node5 = b'\x05' * 32
    node6 = b'\x06' * 32

    # First node from Japan/Tokyo - should get NEW_COUNTRY and NEW_CITY bonus
    is_new_country, is_new_city, country_score, city_score = engine.register_node_location(node4, "JP", "Tokyo")
    assert is_new_country == True
    assert is_new_city == True
    assert country_score > 0
    assert city_score > 0
    logger.info(f"  💍 RING (GEOGRAPHY): JP/Tokyo first node = NEW_COUNTRY + NEW_CITY")

    # Second node from Japan/Tokyo - no bonuses
    is_new_country, is_new_city, country_score2, city_score2 = engine.register_node_location(node5, "JP", "Tokyo")
    assert is_new_country == False
    assert is_new_city == False
    assert country_score2 <= country_score  # Lower score due to more nodes
    assert city_score2 <= city_score
    logger.info(f"  💍 RING (GEOGRAPHY): JP/Tokyo second node (lower scores)")

    # First node from Germany/Berlin - NEW_COUNTRY and NEW_CITY bonus
    is_new_country, is_new_city, country_score3, city_score3 = engine.register_node_location(node6, "DE", "Berlin")
    assert is_new_country == True
    assert is_new_city == True
    logger.info(f"  💍 RING (GEOGRAPHY): DE/Berlin first node (new country bonus)")

    # Check country distribution
    country_dist = engine.get_country_distribution()
    assert len(country_dist) == 2  # JP and DE
    assert country_dist["JP"] == 2
    assert country_dist["DE"] == 1
    logger.info(f"  GEOGRAPHY: {len(country_dist)} unique countries")

    # Check city distribution
    city_dist = engine.get_city_distribution()
    assert len(city_dist) == 2  # Tokyo and Berlin
    logger.info(f"  GEOGRAPHY: {len(city_dist)} unique cities")

    # Check network diversity
    diversity = engine.get_geographic_diversity_score()
    assert diversity > 0
    logger.info(f"  GEOGRAPHY: Network diversity = {diversity:.3f}")

    # Test city hash anonymity
    hash1 = engine.compute_city_hash("JP", "Tokyo")
    hash2 = engine.compute_city_hash("JP", "tokyo")  # Case insensitive
    assert hash1 == hash2
    logger.info("  GEOGRAPHY: City hash is case-insensitive (privacy preserved)")

    # =========================================================================
    # Test HANDSHAKE dimension (PINKY - 5%) - mutual trust between veterans
    # =========================================================================
    logger.info("")
    logger.info("  🤙 PINKY (HANDSHAKE) tests:")

    # Create veteran nodes with saturated fingers
    veteran_jp = b'\x10' * 32  # Japan
    veteran_de = b'\x11' * 32  # Germany
    veteran_us = b'\x12' * 32  # USA
    newbie = b'\x13' * 32       # New node

    # Set up veterans with saturated TIME, INTEGRITY, STORAGE, GEOGRAPHY
    for veteran in [veteran_jp, veteran_de, veteran_us]:
        profile = engine.get_or_create_profile(veteran)
        # Saturate TIME (180 days)
        profile.dimensions[ReputationDimension.TIME].value = 1.0
        profile.dimensions[ReputationDimension.TIME].confidence = 1.0
        # Saturate INTEGRITY
        profile.dimensions[ReputationDimension.INTEGRITY].value = 0.9
        profile.dimensions[ReputationDimension.INTEGRITY].confidence = 1.0
        # Saturate STORAGE
        profile.dimensions[ReputationDimension.STORAGE].value = 1.0
        profile.dimensions[ReputationDimension.STORAGE].confidence = 1.0

    # Register different countries
    engine.register_node_location(veteran_jp, "JP", "Tokyo")
    engine.register_node_location(veteran_de, "DE", "Berlin")
    engine.register_node_location(veteran_us, "US", "New York")
    engine.register_node_location(newbie, "FR", "Paris")

    # Test eligibility
    eligible, reason = engine.is_eligible_for_handshake(veteran_jp)
    assert eligible == True
    logger.info(f"     Veteran JP eligible: {eligible}")

    eligible, reason = engine.is_eligible_for_handshake(newbie)
    assert eligible == False  # Newbie has low TIME
    logger.info(f"     Newbie not eligible: {reason}")

    # Test handshake request validation
    success, msg = engine.request_handshake(veteran_jp, veteran_de)
    assert success == True
    logger.info(f"     Request JP->DE: {msg}")

    # Test same country rejection
    veteran_jp2 = b'\x14' * 32
    profile_jp2 = engine.get_or_create_profile(veteran_jp2)
    profile_jp2.dimensions[ReputationDimension.TIME].value = 1.0
    profile_jp2.dimensions[ReputationDimension.TIME].confidence = 1.0
    profile_jp2.dimensions[ReputationDimension.INTEGRITY].value = 0.9
    profile_jp2.dimensions[ReputationDimension.INTEGRITY].confidence = 1.0
    profile_jp2.dimensions[ReputationDimension.STORAGE].value = 1.0
    profile_jp2.dimensions[ReputationDimension.STORAGE].confidence = 1.0
    engine.register_node_location(veteran_jp2, "JP", "Osaka")

    success, msg = engine.request_handshake(veteran_jp, veteran_jp2)
    assert success == False  # Same country
    assert "Same country" in msg
    logger.info(f"     Same country rejected: {msg}")

    # Form handshake JP <-> DE
    success, msg = engine.form_handshake(
        veteran_jp, veteran_de,
        sig_a=b'\x00' * 64,  # Dummy signature
        sig_b=b'\x00' * 64,
        height=1000
    )
    assert success == True
    logger.info(f"     Handshake JP<->DE formed!")

    # Check handshake count
    count_jp = engine.get_handshake_count(veteran_jp)
    count_de = engine.get_handshake_count(veteran_de)
    assert count_jp == 1
    assert count_de == 1
    logger.info(f"     Handshake counts: JP={count_jp}, DE={count_de}")

    # Check HANDSHAKE dimension updated
    profile_jp = engine.get_profile(veteran_jp)
    handshake_score = profile_jp.dimensions[ReputationDimension.HANDSHAKE].value
    assert handshake_score == 0.1  # 1/10 = 0.1
    logger.info(f"     HANDSHAKE score: {handshake_score:.2f} (1/10)")

    # Form more handshakes
    success, _ = engine.form_handshake(veteran_jp, veteran_us, b'\x00'*64, b'\x00'*64, 1001)
    assert success == True
    count_jp = engine.get_handshake_count(veteran_jp)
    assert count_jp == 2
    logger.info(f"     JP now has {count_jp} handshakes")

    # Test duplicate handshake rejection
    success, msg = engine.form_handshake(veteran_jp, veteran_de, b'\x00'*64, b'\x00'*64, 1002)
    assert success == False
    assert "already exists" in msg
    logger.info(f"     Duplicate rejected: {msg}")

    # Break handshake
    success, msg = engine.break_handshake(veteran_jp, veteran_de, reason="test")
    assert success == True
    count_jp = engine.get_handshake_count(veteran_jp)
    assert count_jp == 1
    logger.info(f"     Handshake broken, JP now has {count_jp} handshake(s)")

    # Get trust web stats
    web_stats = engine.get_trust_web_stats()
    assert web_stats['total_handshakes'] >= 1
    logger.info(f"     Trust web: {web_stats['total_handshakes']} handshakes, {web_stats['nodes_with_handshakes']} nodes")

    # Verify stats include unique_countries and unique_cities
    stats = engine.get_stats()
    assert 'unique_countries' in stats
    assert 'unique_cities' in stats
    logger.info(f"  Stats: {stats['unique_countries']} countries, {stats['unique_cities']} cities")

    logger.info("")
    logger.info("🖐️ All Five Fingers of Adonis self-tests passed!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
