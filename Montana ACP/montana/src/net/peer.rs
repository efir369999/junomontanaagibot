//! Per-peer state and request tracking

use super::message::Message;
use super::rate_limit::{FlowControl, PeerRateLimits};
use super::types::{
    InvItem, PeerState, SyncState, VersionPayload,
    PING_INTERVAL_SECS, REQUEST_TIMEOUT_SECS,
};
use crate::types::{now, Hash, NodeType, PublicKey};
use std::collections::{HashMap, HashSet, VecDeque};
use std::net::SocketAddr;
use std::time::Instant;
use tokio::sync::mpsc;

// =============================================================================
// INVENTORY TRACKING CONSTANTS
// =============================================================================

/// Maximum known inventory items to track per peer.
/// 100k items × 32 bytes = ~3.2MB memory per peer.
///
/// With 125 max peers: 125 × 3.2MB = 400MB worst case.
/// This is acceptable for modern systems.
///
/// Security: Bounded with FIFO eviction to prevent memory exhaustion.
/// FIFO eviction limits set size regardless of attacker's inv announcements.
const MAX_KNOWN_INV: usize = 100_000;

/// Number of oldest entries to evict when at capacity.
/// 10% eviction (10k items) amortizes eviction cost.
///
/// Trade-off:
/// - Too small: frequent evictions, O(n) cost dominates
/// - Too large: more duplicate announcements after eviction
/// - 10% is a reasonable middle ground
const EVICTION_BATCH: usize = 10_000;

pub struct BoundedInvSet {
    set: HashSet<Hash>,
    order: VecDeque<Hash>,
}

impl BoundedInvSet {
    pub fn new() -> Self {
        Self {
            set: HashSet::with_capacity(MAX_KNOWN_INV),
            order: VecDeque::with_capacity(MAX_KNOWN_INV),
        }
    }

    /// Insert hash, evicting oldest entries if at capacity
    pub fn insert(&mut self, hash: Hash) -> bool {
        if self.set.contains(&hash) {
            return false;
        }

        // Evict oldest entries if at capacity
        if self.set.len() >= MAX_KNOWN_INV {
            for _ in 0..EVICTION_BATCH {
                if let Some(old) = self.order.pop_front() {
                    self.set.remove(&old);
                }
            }
        }

        self.set.insert(hash);
        self.order.push_back(hash);
        true
    }

    pub fn contains(&self, hash: &Hash) -> bool {
        self.set.contains(hash)
    }

    pub fn len(&self) -> usize {
        self.set.len()
    }
}

impl Default for BoundedInvSet {
    fn default() -> Self {
        Self::new()
    }
}

/// Connected peer with full state tracking
pub struct Peer {
    // Identity
    pub addr: SocketAddr,
    pub services: u64,
    pub version: u32,
    pub user_agent: String,
    pub node_type: NodeType,

    // Connection
    pub inbound: bool,
    pub state: PeerState,
    pub connected_at: u64,
    pub last_recv: u64,
    pub last_send: u64,
    pub last_ping: u64,
    pub ping_nonce: Option<u64>,
    pub latency_ms: Option<u64>,

    // Traffic
    pub bytes_recv: u64,
    pub bytes_sent: u64,
    pub messages_recv: u64,
    pub messages_sent: u64,

    // Inventory (bounded to prevent memory exhaustion)
    pub known_inv: BoundedInvSet,
    pub inv_to_send: VecDeque<InvItem>,

    // Request tracking
    pub requests_in_flight: HashMap<Hash, Instant>,
    pub last_getaddr: u64,

    // Sync state
    pub best_known_slice: u64,
    pub last_common_slice: Option<u64>,
    pub sync_state: SyncState,
    pub headers_sync_timeout: Option<Instant>,

    // ACP presence
    pub last_presence_tau2: u64,
    pub pubkey: Option<PublicKey>,

    // Communication channel
    pub tx: mpsc::Sender<Message>,

    // Misbehavior
    pub ban_score: u32,

    // Rate limiting (DoS protection)
    pub rate_limits: PeerRateLimits,

    // Flow control (buffer management)
    pub flow_control: FlowControl,

    // Relay timing (for eviction scoring)
    pub last_tx_time: u64,
    pub last_slice_time: u64,

    // Permission flags
    pub has_noban: bool,
}

impl Peer {
    pub fn new(
        addr: SocketAddr,
        inbound: bool,
        tx: mpsc::Sender<Message>,
    ) -> Self {
        let now = now();
        Self {
            addr,
            services: 0,
            version: 0,
            user_agent: String::new(),
            node_type: NodeType::Full,
            inbound,
            state: PeerState::Connecting,
            connected_at: now,
            last_recv: now,
            last_send: now,
            last_ping: 0,
            ping_nonce: None,
            latency_ms: None,
            bytes_recv: 0,
            bytes_sent: 0,
            messages_recv: 0,
            messages_sent: 0,
            known_inv: BoundedInvSet::new(),
            inv_to_send: VecDeque::new(),
            requests_in_flight: HashMap::new(),
            last_getaddr: 0,
            best_known_slice: 0,
            last_common_slice: None,
            sync_state: SyncState::Idle,
            headers_sync_timeout: None,
            last_presence_tau2: 0,
            pubkey: None,
            tx,
            ban_score: 0,
            rate_limits: PeerRateLimits::new(),
            flow_control: FlowControl::new(),
            last_tx_time: 0,
            last_slice_time: 0,
            has_noban: false,
        }
    }

    /// Apply version message
    pub fn apply_version(&mut self, version: &VersionPayload) {
        self.version = version.version;
        self.services = version.services;
        self.user_agent = version.user_agent.clone();
        self.node_type = version.node_type;
        self.best_known_slice = version.best_slice;
        // Only transition to Handshaking if still Connecting
        // Don't reset Ready state (can receive Version after Verack in outbound case)
        if self.state == PeerState::Connecting {
            self.state = PeerState::Handshaking;
        }
    }

    /// Complete handshake
    pub fn handshake_complete(&mut self) {
        self.state = PeerState::Ready;
    }

    /// Create a ready peer (for insertion after handshake)
    pub fn new_ready(
        addr: SocketAddr,
        inbound: bool,
        tx: mpsc::Sender<Message>,
    ) -> Self {
        let mut peer = Self::new(addr, inbound, tx);
        peer.state = PeerState::Ready;
        peer
    }

    /// Check if handshake is complete
    pub fn is_ready(&self) -> bool {
        self.state == PeerState::Ready
    }

    /// Mark message received
    pub fn on_message_recv(&mut self, size: usize) {
        self.last_recv = now();
        self.bytes_recv += size as u64;
        self.messages_recv += 1;
    }

    /// Mark message sent
    pub fn on_message_sent(&mut self, size: usize) {
        self.last_send = now();
        self.bytes_sent += size as u64;
        self.messages_sent += 1;
    }

    /// Add inventory item to send queue
    pub fn push_inv(&mut self, inv: InvItem) {
        if !self.known_inv.contains(&inv.hash) {
            self.inv_to_send.push_back(inv);
        }
    }

    /// Mark inventory as known (received or sent)
    /// BoundedInvSet handles eviction automatically with FIFO policy
    pub fn add_known_inv(&mut self, hash: Hash) {
        self.known_inv.insert(hash);
    }

    /// Check if peer knows about this inventory
    pub fn has_inv(&self, hash: &Hash) -> bool {
        self.known_inv.contains(hash)
    }

    /// Get pending inventory to send (up to limit)
    pub fn get_inv_to_send(&mut self, limit: usize) -> Vec<InvItem> {
        let mut result = Vec::with_capacity(limit.min(self.inv_to_send.len()));
        while result.len() < limit {
            if let Some(inv) = self.inv_to_send.pop_front() {
                if !self.known_inv.contains(&inv.hash) {
                    self.known_inv.insert(inv.hash);
                    result.push(inv);
                }
            } else {
                break;
            }
        }
        result
    }

    /// Track outgoing request
    pub fn track_request(&mut self, hash: Hash) {
        self.requests_in_flight.insert(hash, Instant::now());
    }

    /// Complete request
    pub fn complete_request(&mut self, hash: &Hash) -> Option<Instant> {
        self.requests_in_flight.remove(hash)
    }

    /// Check for timed-out requests
    pub fn get_timed_out_requests(&mut self) -> Vec<Hash> {
        let timeout = std::time::Duration::from_secs(REQUEST_TIMEOUT_SECS);
        let now = Instant::now();
        let timed_out: Vec<Hash> = self
            .requests_in_flight
            .iter()
            .filter(|(_, sent)| now.duration_since(**sent) > timeout)
            .map(|(hash, _)| *hash)
            .collect();

        for hash in &timed_out {
            self.requests_in_flight.remove(hash);
        }

        timed_out
    }

    /// Check if peer needs ping
    pub fn needs_ping(&self) -> bool {
        self.ping_nonce.is_none()
            && now().saturating_sub(self.last_send) > PING_INTERVAL_SECS
    }

    /// Start ping
    pub fn start_ping(&mut self) -> u64 {
        let nonce = rand::random();
        self.ping_nonce = Some(nonce);
        self.last_ping = now();
        nonce
    }

    /// Complete ping with pong
    pub fn complete_ping(&mut self, nonce: u64) -> bool {
        if self.ping_nonce == Some(nonce) {
            let rtt = now().saturating_sub(self.last_ping);
            self.latency_ms = Some(rtt * 1000);
            self.ping_nonce = None;
            true
        } else {
            false
        }
    }

    /// Add to ban score
    pub fn misbehaving(&mut self, score: u32, reason: &str) -> bool {
        self.ban_score = self.ban_score.saturating_add(score);
        tracing::warn!(
            "Peer {} misbehaving (+{}): {} (total: {})",
            self.addr,
            score,
            reason,
            self.ban_score
        );
        self.ban_score >= 100
    }

    /// Check if peer should be banned
    pub fn should_ban(&self) -> bool {
        self.ban_score >= 100
    }

    /// Update best known slice
    pub fn update_best_slice(&mut self, index: u64) {
        if index > self.best_known_slice {
            self.best_known_slice = index;
        }
    }

    /// Check if peer is syncing
    pub fn is_syncing(&self) -> bool {
        matches!(self.sync_state, SyncState::HeaderSync | SyncState::SliceSync)
    }

    /// Start header sync
    pub fn start_header_sync(&mut self) {
        self.sync_state = SyncState::HeaderSync;
        self.headers_sync_timeout = Some(Instant::now());
    }

    /// Start slice sync
    pub fn start_slice_sync(&mut self) {
        self.sync_state = SyncState::SliceSync;
    }

    /// Mark as synced
    pub fn mark_synced(&mut self) {
        self.sync_state = SyncState::Synced;
        self.headers_sync_timeout = None;
    }

    /// Send message through channel
    pub async fn send(&self, msg: Message) -> bool {
        self.tx.send(msg).await.is_ok()
    }

    /// Try send without blocking
    pub fn try_send(&self, msg: Message) -> bool {
        self.tx.try_send(msg).is_ok()
    }
}

/// Peer info for external queries
#[derive(Debug, Clone)]
pub struct PeerInfo {
    pub addr: SocketAddr,
    pub services: u64,
    pub version: u32,
    pub user_agent: String,
    pub inbound: bool,
    pub is_ready: bool,
    pub connected_at: u64,
    pub last_recv: u64,
    pub last_send: u64,
    pub bytes_recv: u64,
    pub bytes_sent: u64,
    pub latency_ms: Option<u64>,
    pub best_known_slice: u64,
    pub sync_state: SyncState,
    pub ban_score: u32,
    /// Last time this peer relayed a transaction (for eviction scoring)
    pub last_tx_time: u64,
    /// Last time this peer relayed a slice (for eviction scoring)
    pub last_slice_time: u64,
    /// Permission: protected from banning
    pub has_noban: bool,
}

impl From<&Peer> for PeerInfo {
    fn from(peer: &Peer) -> Self {
        Self {
            addr: peer.addr,
            services: peer.services,
            version: peer.version,
            user_agent: peer.user_agent.clone(),
            inbound: peer.inbound,
            is_ready: peer.is_ready(),
            connected_at: peer.connected_at,
            last_recv: peer.last_recv,
            last_send: peer.last_send,
            bytes_recv: peer.bytes_recv,
            bytes_sent: peer.bytes_sent,
            latency_ms: peer.latency_ms,
            best_known_slice: peer.best_known_slice,
            sync_state: peer.sync_state,
            ban_score: peer.ban_score,
            last_tx_time: peer.last_tx_time,
            last_slice_time: peer.last_slice_time,
            has_noban: peer.has_noban,
        }
    }
}
