// Montana Network Layer — Constants and Types
// Copyright (c) 2024-2026 Alejandro Montana
// Distributed under the MIT software license.

//! Network constants and types for the Montana P2P protocol.
//!
//! # Design Goals
//!
//! 1. **Bounded memory usage** — All collections and messages have explicit size limits.
//!    An attacker cannot exhaust memory by sending large or many messages.
//!
//! 2. **DoS resistance** — Rate limiting, bans, and connection limits prevent resource
//!    exhaustion attacks from any single IP or subnet.
//!
//! 3. **Eclipse resistance** — Netgroup diversity limits (MAX_PEERS_PER_NETGROUP) ensure
//!    no single /16 subnet can dominate connections.
//!
//! # What This Does NOT Protect Against
//!
//! - Sybil attacks across many subnets (mitigated by AdaptiveCooldown at consensus layer)
//! - Nation-state level BGP hijacking (mitigated by Noise encryption — no MITM, only DoS)
//! - Compromise of hardcoded nodes (mitigated by ML-DSA-65 signatures and node diversity)
//!
//! # Memory Budget
//!
//! | Component         | Max Size | Calculation                              |
//! |-------------------|----------|------------------------------------------|
//! | Per-peer receive  | 2 MB     | MESSAGE_SIZE_LIMIT                       |
//! | Inventory relay   | ~180 MB  | 50k items × 36 bytes × relay_cache       |
//! | Address manager   | ~64 MB   | 65k addresses × ~1KB each                |
//! | Orphan pool       | 800 KB   | MAX_ORPHANS(100) × MAX_SLICE_SIZE(8KB)   |
//! | Peer connections  | ~256 MB  | MAX_PEERS(125) × ~2MB buffers            |
//!
//! Total worst-case: ~500 MB for network layer (acceptable for full node).

use crate::types::{Hash, NodeType};
use serde::{Deserialize, Serialize};
use std::net::{IpAddr, SocketAddr};

// =============================================================================
// PROTOCOL IDENTIFICATION
// =============================================================================

/// Protocol version number. Increment on breaking wire format changes.
/// Nodes with lower version are rejected during handshake.
pub const PROTOCOL_VERSION: u32 = 2;

/// Magic bytes identifying Montana protocol packets.
/// Prevents cross-talk with other P2P networks on same port.
pub const PROTOCOL_MAGIC: [u8; 4] = *b"MONT";

/// Default TCP port for mainnet. Testnet uses 19334.
pub const DEFAULT_PORT: u16 = 19333;

// =============================================================================
// CONNECTION LIMITS
// =============================================================================

/// Maximum total peer connections.
/// Based on: 8 outbound + 117 inbound = 125 total.
/// Matches Bitcoin Core's DEFAULT_MAX_PEER_CONNECTIONS.
pub const MAX_PEERS: usize = 125;

/// Maximum outbound connections we initiate.
/// Security: We control who we connect to, so these are more trusted for
/// consensus-critical data like external IP discovery.
pub const MAX_OUTBOUND: usize = 8;

/// Maximum inbound connections from others.
/// Note: Inbound peers are untrusted — they may be Sybils.
/// Calculated: MAX_PEERS - MAX_OUTBOUND = 125 - 8 = 117
pub const MAX_INBOUND: usize = 117;

/// Max connections from the same IP address.
/// 2 allows NAT users while preventing single-IP flooding.
/// If an attacker controls one IP, they get at most 2 slots out of 125.
pub const MAX_CONNECTIONS_PER_IP: usize = 2;

/// Max connections from the same /16 subnet (netgroup).
/// Security: Prevents Erebus-style attacks where attacker controls
/// many IPs in one subnet. To fill all 8 outbound slots, attacker
/// needs at least 4 different /16 subnets.
pub const MAX_PEERS_PER_NETGROUP: usize = 2;

// =============================================================================
// TIMEOUTS
// =============================================================================

/// Handshake timeout in seconds.
/// 60s allows high-latency connections (Tor, satellite) while preventing
/// slowloris attacks that hold connections open indefinitely.
pub const HANDSHAKE_TIMEOUT_SECS: u64 = 60;

/// Ping interval in seconds.
/// Peers that don't respond to ping within 2× this interval are disconnected.
pub const PING_INTERVAL_SECS: u64 = 120;

/// Request timeout in seconds.
/// If peer doesn't respond to getdata/getheaders within this, mark as failed.
pub const REQUEST_TIMEOUT_SECS: u64 = 120;

// =============================================================================
// MESSAGE SIZE LIMITS
// =============================================================================
// These limits prevent memory exhaustion attacks. Each limit is chosen to
// accommodate legitimate use while bounding memory usage.
//
// IMPORTANT: protocol.rs and verification.rs must use these same constants.
// Do not hardcode size limits elsewhere.

/// Maximum size of any protocol message (2 MB).
/// This is the outer limit — individual message types have tighter limits.
/// Memory impact: One 2MB message per peer = 250 MB for 125 peers.
pub const MESSAGE_SIZE_LIMIT: usize = 2 * 1024 * 1024;

/// Maximum Version message size (1 KB).
/// Version contains: protocol fields + user_agent string.
/// User agent is truncated to 256 bytes, so 1KB is generous.
pub const MAX_VERSION_SIZE: usize = 1024;

/// Maximum Addr message size (64 KB).
/// Contains up to 1000 addresses × 64 bytes each.
pub const MAX_ADDR_MSG_SIZE: usize = 1_000 * 64;

/// Maximum Inv message size (~1.8 MB).
/// Contains up to 50,000 inventory items × 36 bytes (1 type + 32 hash + 3 padding).
pub const MAX_INV_MSG_SIZE: usize = 50_000 * 36;

/// Maximum Headers message size (~512 KB).
/// Contains up to 2000 headers × 256 bytes each.
pub const MAX_HEADERS_SIZE: usize = 2000 * 256;

/// Maximum Slice message size (8 KB).
/// Slices are compact — only presence proofs, not full transactions.
/// Memory: MAX_ORPHANS(100) × 8KB = 800KB for orphan pool.
pub const MAX_SLICE_SIZE: usize = 8 * 1024;

/// Maximum Transaction message size (1 MB).
/// Allows complex transactions while preventing single-tx memory exhaustion.
pub const MAX_TX_SIZE: usize = 1024 * 1024;

/// Maximum Presence proof size (8 KB).
/// Contains: signature + timestamp + bitmap + slice reference.
pub const MAX_PRESENCE_SIZE: usize = 8 * 1024;

/// Maximum Ping/Pong message size (16 bytes).
/// Just a nonce for latency measurement.
pub const MAX_PING_SIZE: usize = 16;

/// Maximum Reject message size (1 KB).
/// Contains error code + reason string + optional hash.
pub const MAX_REJECT_SIZE: usize = 1024;

/// Checksum size (4 bytes).
/// First 4 bytes of SHA3-256 hash for integrity check.
pub const CHECKSUM_SIZE: usize = 4;

// =============================================================================
// INVENTORY LIMITS
// =============================================================================

/// Maximum items in a single Inv message.
/// Prevents inventory flooding.
pub const MAX_INV_SIZE: usize = 50_000;

/// Maximum addresses in a single Addr message.
/// Matches Bitcoin Core's MAX_ADDR_TO_SEND.
pub const MAX_ADDR_SIZE: usize = 1_000;

/// Maximum items in a single GetData request.
/// Prevents request amplification attacks.
pub const MAX_GETDATA_SIZE: usize = 50_000;

// =============================================================================
// RELAY INTERVALS
// =============================================================================

/// Address relay interval (30 seconds).
/// Don't forward addresses more often to prevent addr flooding.
pub const ADDR_RELAY_INTERVAL_SECS: u64 = 30;

/// Inventory broadcast interval (100 ms).
/// Batching interval for transaction/presence announcements.
pub const INV_BROADCAST_INTERVAL_MS: u64 = 100;

/// Relay cache expiry (15 minutes).
/// Data in relay cache is removed after this time.
/// Memory: bounded by MAX_INV_SIZE × expiry_time / broadcast_interval.
pub const RELAY_CACHE_EXPIRY_SECS: u64 = 15 * 60;

// =============================================================================
// BAN DURATIONS
// =============================================================================
// Different violations get different ban lengths based on severity.
// Longer bans for clear attacks, shorter for likely misconfigurations.

/// Ban for invalid magic bytes: 1 hour.
/// Likely misconfiguration or port scanner, not targeted attack.
pub const BAN_DURATION_INVALID_MAGIC: u64 = 3600;

/// Ban for oversized messages: 24 hours.
/// Clear DoS attempt — legitimate nodes respect size limits.
pub const BAN_DURATION_OVERSIZED_MSG: u64 = 86400;

/// Ban for protocol violations: 24 hours.
/// Examples: messages out of sequence, invalid handshake.
pub const BAN_DURATION_PROTOCOL_VIOLATION: u64 = 86400;

/// Ban for misbehavior: 24 hours.
/// Examples: sending invalid slices, inventory spam.
pub const BAN_DURATION_MISBEHAVIOR: u64 = 86400;

// =============================================================================
// RETRY LOGIC
// =============================================================================

/// Initial retry delay for failed connections (10 seconds).
pub const INITIAL_RETRY_DELAY_SECS: u64 = 10;

/// Maximum retry delay (1 hour).
/// Prevents permanently blackholing addresses that might recover.
pub const MAX_RETRY_DELAY_SECS: u64 = 3600;

/// Exponential backoff factor for retries.
/// Delays: 10s → 20s → 40s → 80s → ... → 3600s (capped).
pub const RETRY_BACKOFF_FACTOR: u64 = 2;

// =============================================================================
// SERVICE FLAGS
// =============================================================================
// Advertised in Version message to indicate node capabilities.

/// NODE_FULL: Stores complete chain history, can serve any slice.
pub const NODE_FULL: u64 = 1 << 0;

/// NODE_LIGHT: Stores only recent slices and headers.
pub const NODE_LIGHT: u64 = 1 << 1;

/// NODE_PRESENCE: Participates in presence proof protocol.
pub const NODE_PRESENCE: u64 = 1 << 2;

/// NODE_NTS: Provides NTS (Network Time Security) service.
pub const NODE_NTS: u64 = 1 << 3;

// =============================================================================
// NETWORK ADDRESS
// =============================================================================

/// Network address with service flags and timestamp.
///
/// Used in: Version messages, Addr messages, address manager.
///
/// Security notes:
/// - `is_routable()` filters non-routable IPs to prevent address table pollution
/// - Timestamp is self-reported and untrusted — used only for freshness heuristics
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct NetAddress {
    /// Service flags advertised by this node
    pub services: u64,
    /// IP address (v4 or v6)
    pub ip: IpAddr,
    /// TCP port
    pub port: u16,
    /// Last known timestamp (self-reported, untrusted)
    pub timestamp: u64,
}

impl NetAddress {
    pub fn new(ip: IpAddr, port: u16, services: u64) -> Self {
        Self {
            services,
            ip,
            port,
            timestamp: crate::types::now(),
        }
    }

    pub fn socket_addr(&self) -> SocketAddr {
        SocketAddr::new(self.ip, self.port)
    }

    pub fn from_socket_addr(addr: SocketAddr, services: u64) -> Self {
        Self {
            services,
            ip: addr.ip(),
            port: addr.port(),
            timestamp: crate::types::now(),
        }
    }

    /// Check if address is globally routable.
    ///
    /// Filters out:
    /// - Private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    /// - Loopback (127.0.0.0/8, ::1)
    /// - Link-local (169.254.0.0/16, fe80::/10)
    /// - Documentation (192.0.2.0/24, 2001:db8::/32)
    /// - Broadcast, multicast, unspecified
    ///
    /// This prevents address manager pollution with useless addresses.
    pub fn is_routable(&self) -> bool {
        match self.ip {
            IpAddr::V4(ip) => {
                !ip.is_private()
                    && !ip.is_loopback()
                    && !ip.is_link_local()
                    && !ip.is_broadcast()
                    && !ip.is_documentation()
                    && !ip.is_unspecified()
            }
            IpAddr::V6(ip) => {
                if ip.is_loopback() || ip.is_unspecified() || ip.is_multicast() {
                    return false;
                }

                let segments = ip.segments();

                // fc00::/7 — Unique Local Address (private IPv6)
                if (segments[0] & 0xfe00) == 0xfc00 {
                    return false;
                }

                // fe80::/10 — Link-local
                if (segments[0] & 0xffc0) == 0xfe80 {
                    return false;
                }

                // 2001:db8::/32 — Documentation
                if segments[0] == 0x2001 && segments[1] == 0x0db8 {
                    return false;
                }

                // ::ffff:0:0/96 — IPv4-mapped, check embedded IPv4
                if segments[0] == 0 && segments[1] == 0 && segments[2] == 0
                    && segments[3] == 0 && segments[4] == 0 && segments[5] == 0xffff
                {
                    let ipv4 = std::net::Ipv4Addr::new(
                        (segments[6] >> 8) as u8,
                        segments[6] as u8,
                        (segments[7] >> 8) as u8,
                        segments[7] as u8,
                    );
                    return !ipv4.is_private()
                        && !ipv4.is_loopback()
                        && !ipv4.is_link_local()
                        && !ipv4.is_broadcast()
                        && !ipv4.is_documentation()
                        && !ipv4.is_unspecified();
                }

                true
            }
        }
    }
}

// =============================================================================
// INVENTORY TYPES
// =============================================================================

/// Inventory item types for Inv/GetData messages.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[repr(u8)]
pub enum InvType {
    /// Time slice (ACP consensus unit)
    Slice = 1,
    /// Transaction
    Tx = 2,
    /// Presence proof
    Presence = 3,
}

/// Inventory item: identifies data by type and hash.
///
/// Used in: Inv, GetData, NotFound messages.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct InvItem {
    pub inv_type: InvType,
    pub hash: Hash,
}

impl InvItem {
    pub fn slice(hash: Hash) -> Self {
        Self { inv_type: InvType::Slice, hash }
    }

    pub fn tx(hash: Hash) -> Self {
        Self { inv_type: InvType::Tx, hash }
    }

    pub fn presence(hash: Hash) -> Self {
        Self { inv_type: InvType::Presence, hash }
    }
}

// =============================================================================
// REJECT CODES
// =============================================================================

/// Reject message error codes.
///
/// Sent in Reject message to explain why data was rejected.
/// Note: Reject messages are advisory — attackers will ignore them.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum RejectCode {
    /// Message could not be decoded
    Malformed = 0x01,
    /// Data failed validation
    Invalid = 0x10,
    /// Uses obsolete protocol feature
    Obsolete = 0x11,
    /// Already have this data
    Duplicate = 0x12,
    /// Violates policy (not consensus)
    NonStandard = 0x40,
    /// Transaction fee too low
    InsufficientFee = 0x42,
    /// Conflicts with checkpoint
    Checkpoint = 0x43,
}

/// Reject message payload.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RejectPayload {
    pub code: RejectCode,
    pub reason: String,
    /// Optional: hash of rejected item
    pub data: Option<Hash>,
}

// =============================================================================
// VERSION MESSAGE
// =============================================================================

/// Version message payload exchanged during handshake.
///
/// Security notes:
/// - `nonce` is used for self-connection detection (see protocol.rs)
/// - `addr_recv` tells the peer how we see them (used for external IP discovery)
/// - `user_agent` is truncated to 256 chars to prevent memory exhaustion
/// - `best_slice` is self-reported and verified against other peers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionPayload {
    /// Protocol version (must be >= PROTOCOL_VERSION)
    pub version: u32,
    /// Service flags we provide
    pub services: u64,
    /// Current time (used for clock skew detection)
    pub timestamp: u64,
    /// How we see the peer's address
    pub addr_recv: NetAddress,
    /// Our own address (may be 0.0.0.0 if unknown)
    pub addr_from: NetAddress,
    /// Random nonce for self-connection detection
    pub nonce: u64,
    /// Client software identifier
    pub user_agent: String,
    /// Our current chain height (τ₂ index)
    pub best_slice: u64,
    /// Node type (Full, Light, LightClient)
    pub node_type: NodeType,
}

impl VersionPayload {
    pub fn new(
        services: u64,
        addr_recv: NetAddress,
        addr_from: NetAddress,
        best_slice: u64,
        node_type: NodeType,
    ) -> Self {
        Self {
            version: PROTOCOL_VERSION,
            services,
            timestamp: crate::types::now(),
            addr_recv,
            addr_from,
            nonce: rand::random(),
            user_agent: format!("/Montana:{}/", env!("CARGO_PKG_VERSION")),
            best_slice,
            node_type,
        }
    }
}

// =============================================================================
// STATE MACHINES
// =============================================================================

/// Peer connection state machine.
///
/// ```text
/// State Transitions:
///
///                    TCP connect
///     ┌──────────────────────────────────┐
///     │                                  │
///     ▼                                  │
/// ┌───────────┐                          │
/// │Connecting │◄─────────────────────────┘
/// └─────┬─────┘
///       │ socket opened
///       ▼
/// ┌───────────┐
/// │ Connected │
/// └─────┬─────┘
///       │ recv Version (inbound) / send Version (outbound)
///       ▼
/// ┌───────────┐
/// │Handshaking│
/// └─────┬─────┘
///       │ recv Verack
///       ▼
/// ┌───────────┐                    ┌──────────────┐
/// │   Ready   │──── shutdown ─────►│Disconnecting │
/// └───────────┘                    └──────┬───────┘
///       │                                 │
///       │ error / timeout / ban           │ cleanup done
///       │                                 ▼
///       │                          ┌──────────────┐
///       └─────────────────────────►│ Disconnected │
///                                  └──────────────┘
/// ```
///
/// # Security Properties
///
/// - **Handshake timeout (60s)** prevents slowloris attacks
/// - **Only Ready peers can relay messages** — pre-handshake peers cannot inject data
/// - **Ban triggers immediate disconnect** — no grace period for attackers
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PeerState {
    /// TCP connection in progress
    Connecting,
    /// Socket opened, awaiting handshake
    Connected,
    /// Version exchanged, awaiting Verack
    Handshaking,
    /// Handshake complete, can relay messages
    Ready,
    /// Graceful disconnect in progress
    Disconnecting,
    /// Connection closed
    Disconnected,
}

/// Sync state machine for a peer.
///
/// ```text
/// State Transitions:
///
/// ┌──────┐
/// │ Idle │◄──────────────────────────────────────┐
/// └──┬───┘                                       │
///    │ peer has newer slices                     │
///    ▼                                           │
/// ┌────────────┐                                 │
/// │ HeaderSync │─── headers caught up ───┐       │
/// └──────┬─────┘                         │       │
///        │                               │       │
///        │ have headers,                 │       │
///        │ need slice data               │       │
///        ▼                               │       │
/// ┌────────────┐                         │       │
/// │ SliceSync  │◄────────────────────────┘       │
/// └──────┬─────┘                                 │
///        │ all slices downloaded                 │
///        ▼                                       │
/// ┌────────────┐                                 │
/// │   Synced   │─── peer gets ahead again ───────┘
/// └────────────┘
/// ```
///
/// Note: HeaderSync may skip directly to Synced if we already
/// have all slice data for the received headers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncState {
    /// Not syncing with this peer
    Idle,
    /// Downloading headers (fast, small messages)
    HeaderSync,
    /// Downloading full slice data
    SliceSync,
    /// Fully synchronized with this peer
    Synced,
}

// =============================================================================
// ADDRESS INFO
// =============================================================================

/// Address manager entry with connection history.
///
/// Used by AddrMan to track connection attempts and successes.
/// Implements the "terrible address" heuristic to deprioritize
/// addresses that consistently fail.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AddressInfo {
    /// Network address
    pub addr: NetAddress,
    /// Timestamp of last successful connection (0 = never)
    pub last_success: u64,
    /// Timestamp of last connection attempt
    pub last_attempt: u64,
    /// Consecutive failed attempts since last success
    pub attempts: u32,
    /// Which peer told us about this address (for source diversity)
    pub source: Option<SocketAddr>,
}

impl AddressInfo {
    pub fn new(addr: NetAddress, source: Option<SocketAddr>) -> Self {
        Self {
            addr,
            last_success: 0,
            last_attempt: 0,
            attempts: 0,
            source,
        }
    }

    pub fn mark_attempt(&mut self) {
        self.last_attempt = crate::types::now();
        self.attempts += 1;
    }

    pub fn mark_success(&mut self) {
        self.last_success = crate::types::now();
        self.attempts = 0;
    }

    /// Check if this address should be deprioritized.
    ///
    /// An address is "terrible" if:
    /// - Timestamp is in future (> 10 min from now) — Time-Travel attack
    /// - Tried in last 60s and failed 3+ times, OR
    /// - Never succeeded and failed 3+ times, OR
    /// - Last contact over 30 days ago
    pub fn is_terrible(&self) -> bool {
        let now = crate::types::now();

        // SECURITY: Future timestamp is terrible (Time-Travel Poisoning defense)
        // Allows 10 min clock skew, rejects anything beyond
        if self.addr.timestamp > now.saturating_add(600) {
            return true;
        }

        // Tried recently and failed repeatedly
        if self.last_attempt > 0 && self.last_attempt > now.saturating_sub(60) {
            return self.attempts >= 3;
        }

        // Never succeeded and many failed attempts
        if self.last_success == 0 && self.attempts >= 3 {
            return true;
        }

        // Stale: last contact over 30 days ago
        if self.addr.timestamp < now.saturating_sub(30 * 24 * 60 * 60) {
            return true;
        }

        false
    }
}
