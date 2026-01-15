//! Inventory relay cache

use super::types::{InvItem, InvType, RELAY_CACHE_EXPIRY_SECS, REQUEST_TIMEOUT_SECS};

/// Maximum relay cache entries
/// Prevents memory exhaustion from flood of unique items
/// 10000 × ~1KB average = ~10MB max memory for cache
const MAX_RELAY_CACHE_ENTRIES: usize = 10_000;

/// Maximum relay cache total size in bytes
/// Hard limit prevents large items from exceeding memory budget
/// 50MB = 50 × 1024 × 1024
const MAX_RELAY_CACHE_BYTES: usize = 50 * 1024 * 1024;

/// Maximum entries in have_tx and have_presence sets
/// Each Hash is 32 bytes, so 100k entries = ~3.2MB per set
const MAX_HAVE_ENTRIES: usize = 100_000;

/// Number of entries to evict when limit is reached
/// Evicting 10% at a time amortizes the cost
const EVICTION_BATCH_SIZE: usize = 10_000;

/// Maximum in-flight requests per peer (Bitcoin Core: MAX_PEER_TX_REQUEST_IN_FLIGHT = 100)
/// Security: Prevents single peer from exhausting request tracking memory
/// With 125 peers × 100 requests = 12,500 max entries = ~1 MB
const MAX_PEER_REQUEST_IN_FLIGHT: usize = 100;

use crate::types::{now, Hash};
use std::collections::{HashMap, HashSet, VecDeque};
use std::net::SocketAddr;
use std::time::Instant;

// =============================================================================
// LRU HASH SET
// =============================================================================

/// LRU-evicting HashSet for inventory tracking
///
/// Provides O(1) contains/insert with bounded memory.
/// When capacity is exceeded, oldest entries are evicted in batches.
///
/// Security: Prevents memory exhaustion from flood of unique items.
/// Gradual eviction avoids sudden memory spikes that could occur
/// with full clear().
struct LruHashSet {
    /// Fast lookup set
    set: HashSet<Hash>,
    /// Insertion order for LRU eviction (front = oldest)
    order: VecDeque<Hash>,
    /// Maximum entries before eviction
    max_size: usize,
    /// Entries to evict per batch
    batch_size: usize,
}

impl LruHashSet {
    fn new(max_size: usize, batch_size: usize) -> Self {
        Self {
            set: HashSet::with_capacity(max_size),
            order: VecDeque::with_capacity(max_size),
            max_size,
            batch_size,
        }
    }

    /// Insert hash, evicting oldest if at capacity
    fn insert(&mut self, hash: Hash) -> bool {
        // Check capacity before insert
        if self.set.len() >= self.max_size {
            self.evict_oldest_batch();
        }

        if self.set.insert(hash) {
            self.order.push_back(hash);
            true
        } else {
            false
        }
    }

    /// Check if hash exists
    fn contains(&self, hash: &Hash) -> bool {
        self.set.contains(hash)
    }

    /// Get current size
    fn len(&self) -> usize {
        self.set.len()
    }

    /// Evict oldest entries (FIFO)
    fn evict_oldest_batch(&mut self) {
        let to_evict = self.batch_size.min(self.order.len());
        for _ in 0..to_evict {
            if let Some(hash) = self.order.pop_front() {
                self.set.remove(&hash);
            }
        }
    }
}

/// Request tracking entry
struct RequestEntry {
    peer: SocketAddr,
    requested_at: Instant,
}

/// Relay cache entry
struct RelayEntry {
    data: Vec<u8>,
    received_at: u64,
}

/// Inventory manager
pub struct Inventory {
    // Items we have locally
    // Slices use HashSet (bounded by chain length, not attacker-controlled)
    have_slice: HashSet<Hash>,
    // Tx and Presence use LruHashSet (attacker can flood with unique items)
    have_tx: LruHashSet,
    have_presence: LruHashSet,

    // Items we've requested from peers
    requested: HashMap<Hash, RequestEntry>,

    // Per-peer request count (for MAX_PEER_REQUEST_IN_FLIGHT enforcement)
    requests_per_peer: HashMap<SocketAddr, usize>,

    // Items recently relayed (cache for deduplication)
    relay_cache: HashMap<Hash, RelayEntry>,

    // Total bytes in relay_cache (for memory limit enforcement)
    relay_cache_bytes: usize,

    // Items already asked for (to avoid re-requesting too quickly)
    already_asked: HashMap<Hash, u64>,
}

impl Inventory {
    pub fn new() -> Self {
        Self {
            have_slice: HashSet::new(),
            have_tx: LruHashSet::new(MAX_HAVE_ENTRIES, EVICTION_BATCH_SIZE),
            have_presence: LruHashSet::new(MAX_HAVE_ENTRIES, EVICTION_BATCH_SIZE),
            requested: HashMap::new(),
            requests_per_peer: HashMap::new(),
            relay_cache: HashMap::new(),
            relay_cache_bytes: 0,
            already_asked: HashMap::new(),
        }
    }

    /// Check if we have this item locally
    pub fn have(&self, inv: &InvItem) -> bool {
        match inv.inv_type {
            InvType::Slice => self.have_slice.contains(&inv.hash),
            InvType::Tx => self.have_tx.contains(&inv.hash),
            InvType::Presence => self.have_presence.contains(&inv.hash),
        }
    }

    /// Mark item as locally available
    pub fn add_have(&mut self, inv: &InvItem) {
        match inv.inv_type {
            InvType::Slice => {
                self.have_slice.insert(inv.hash);
            }
            InvType::Tx => {
                self.have_tx.insert(inv.hash);
            }
            InvType::Presence => {
                self.have_presence.insert(inv.hash);
            }
        }
        // Remove from requested since we have it now
        self.requested.remove(&inv.hash);
    }

    /// Mark slice as available by hash
    pub fn add_slice(&mut self, hash: Hash) {
        self.have_slice.insert(hash);
        self.requested.remove(&hash);
    }

    /// Mark tx as available by hash
    pub fn add_tx(&mut self, hash: Hash) {
        self.have_tx.insert(hash);
        self.requested.remove(&hash);
    }

    /// Mark presence as available by hash
    pub fn add_presence(&mut self, hash: Hash) {
        self.have_presence.insert(hash);
        self.requested.remove(&hash);
    }

    /// Check if item is already requested
    pub fn is_requested(&self, hash: &Hash) -> bool {
        self.requested.contains_key(hash)
    }

    /// Track request for item from peer
    ///
    /// Returns false if peer has exceeded MAX_PEER_REQUEST_IN_FLIGHT (Bitcoin Core style).
    /// Caller should skip this item or try another peer.
    pub fn request(&mut self, inv: &InvItem, peer: SocketAddr) -> bool {
        // Check per-peer limit (Bitcoin Core: MAX_PEER_TX_REQUEST_IN_FLIGHT)
        let peer_count = self.requests_per_peer.get(&peer).copied().unwrap_or(0);
        if peer_count >= MAX_PEER_REQUEST_IN_FLIGHT {
            return false;
        }

        self.requested.insert(
            inv.hash,
            RequestEntry {
                peer,
                requested_at: Instant::now(),
            },
        );
        *self.requests_per_peer.entry(peer).or_insert(0) += 1;
        self.already_asked.insert(inv.hash, now());
        true
    }

    /// Batch version of request(). Returns items actually requested.
    pub fn request_batch(&mut self, items: &[InvItem], peer: SocketAddr) -> Vec<InvItem> {
        let now_instant = Instant::now();
        let now_ts = now();

        let current_count = self.requests_per_peer.get(&peer).copied().unwrap_or(0);
        let available = MAX_PEER_REQUEST_IN_FLIGHT.saturating_sub(current_count);

        if available == 0 {
            return Vec::new();
        }

        let mut requested_items = Vec::with_capacity(items.len().min(available));
        let mut added_count = 0usize;

        for inv in items {
            if added_count >= available {
                break;
            }

            if self.requested.contains_key(&inv.hash) {
                continue;
            }

            self.requested.insert(
                inv.hash,
                RequestEntry {
                    peer,
                    requested_at: now_instant,
                },
            );
            self.already_asked.insert(inv.hash, now_ts);
            requested_items.push(inv.clone());
            added_count += 1;
        }

        if added_count > 0 {
            *self.requests_per_peer.entry(peer).or_insert(0) += added_count;
        }

        requested_items
    }

    /// Check how many requests are in-flight for a peer
    pub fn peer_request_count(&self, peer: &SocketAddr) -> usize {
        self.requests_per_peer.get(peer).copied().unwrap_or(0)
    }

    /// Check if peer can accept more requests
    pub fn peer_can_request(&self, peer: &SocketAddr) -> bool {
        self.peer_request_count(peer) < MAX_PEER_REQUEST_IN_FLIGHT
    }

    /// Complete request (item received)
    pub fn received(&mut self, hash: &Hash) -> Option<SocketAddr> {
        self.requested.remove(hash).map(|entry| {
            // Decrement per-peer counter
            if let Some(count) = self.requests_per_peer.get_mut(&entry.peer) {
                *count = count.saturating_sub(1);
                if *count == 0 {
                    self.requests_per_peer.remove(&entry.peer);
                }
            }
            entry.peer
        })
    }

    /// Check if we should ask for this item
    /// Returns false if we have it, it's requested, or we asked recently
    pub fn should_request(&self, inv: &InvItem) -> bool {
        if self.have(inv) {
            return false;
        }
        if self.is_requested(&inv.hash) {
            return false;
        }
        // Check if we asked for this recently (within 2 minutes)
        if let Some(&asked_at) = self.already_asked.get(&inv.hash)
            && now().saturating_sub(asked_at) < REQUEST_TIMEOUT_SECS
        {
            return false;
        }
        true
    }

    /// Get list of items we need from an inv announcement
    pub fn filter_needed(&self, items: &[InvItem]) -> Vec<InvItem> {
        items
            .iter()
            .filter(|inv| self.should_request(inv))
            .cloned()
            .collect()
    }

    /// Add to relay cache with size limits
    ///
    /// Memory protection:
    /// - MAX_RELAY_CACHE_ENTRIES (10,000) prevents entry count exhaustion
    /// - MAX_RELAY_CACHE_BYTES (50MB) prevents memory exhaustion from large items
    /// - Oldest entries evicted when limits exceeded
    pub fn cache_relay(&mut self, hash: Hash, data: Vec<u8>) {
        let data_len = data.len();

        // Remove old entry if exists (update case)
        if let Some(old) = self.relay_cache.remove(&hash) {
            self.relay_cache_bytes = self.relay_cache_bytes.saturating_sub(old.data.len());
        }

        // Evict oldest entries if entry count limit exceeded
        while self.relay_cache.len() >= MAX_RELAY_CACHE_ENTRIES {
            self.evict_oldest_relay();
        }

        // Evict oldest entries if byte limit exceeded
        while self.relay_cache_bytes + data_len > MAX_RELAY_CACHE_BYTES
            && !self.relay_cache.is_empty()
        {
            self.evict_oldest_relay();
        }

        // Add new entry
        self.relay_cache_bytes += data_len;
        self.relay_cache.insert(
            hash,
            RelayEntry {
                data,
                received_at: now(),
            },
        );
    }

    /// Evict the oldest relay cache entry
    fn evict_oldest_relay(&mut self) {
        if let Some((&oldest_hash, _)) = self
            .relay_cache
            .iter()
            .min_by_key(|(_, entry)| entry.received_at)
        {
            if let Some(entry) = self.relay_cache.remove(&oldest_hash) {
                self.relay_cache_bytes = self.relay_cache_bytes.saturating_sub(entry.data.len());
            }
        }
    }

    /// Get from relay cache
    pub fn get_relay(&self, hash: &Hash) -> Option<&[u8]> {
        self.relay_cache.get(hash).map(|e| e.data.as_slice())
    }

    /// Check if we have in relay cache
    pub fn has_relay(&self, hash: &Hash) -> bool {
        self.relay_cache.contains_key(hash)
    }

    /// Get timed-out requests and their peers
    pub fn get_timed_out_requests(&mut self) -> Vec<(Hash, SocketAddr)> {
        let timeout = std::time::Duration::from_secs(REQUEST_TIMEOUT_SECS);
        let now = Instant::now();

        let timed_out: Vec<(Hash, SocketAddr)> = self
            .requested
            .iter()
            .filter(|(_, entry)| now.duration_since(entry.requested_at) > timeout)
            .map(|(hash, entry)| (*hash, entry.peer))
            .collect();

        for (hash, peer) in &timed_out {
            self.requested.remove(hash);
            // Decrement per-peer counter
            if let Some(count) = self.requests_per_peer.get_mut(peer) {
                *count = count.saturating_sub(1);
                if *count == 0 {
                    self.requests_per_peer.remove(peer);
                }
            }
        }

        timed_out
    }

    /// Clean up expired entries
    pub fn expire(&mut self) {
        let now_ts = now();

        // Expire relay cache (track bytes removed)
        let mut bytes_removed = 0usize;
        self.relay_cache.retain(|_, entry| {
            let keep = now_ts.saturating_sub(entry.received_at) < RELAY_CACHE_EXPIRY_SECS;
            if !keep {
                bytes_removed += entry.data.len();
            }
            keep
        });
        self.relay_cache_bytes = self.relay_cache_bytes.saturating_sub(bytes_removed);

        // Expire already_asked (keep for 10 minutes)
        self.already_asked.retain(|_, &mut asked_at| {
            now_ts.saturating_sub(asked_at) < 600
        });

        // Note: have_tx and have_presence use LruHashSet with automatic
        // eviction, so no manual cleanup needed here. This is more secure
        // than the previous clear() approach which caused:
        // 1. Sudden memory spikes before clearing
        // 2. Loss of all state (could re-request already-received items)
    }

    /// Get stats
    pub fn stats(&self) -> InventoryStats {
        InventoryStats {
            slices: self.have_slice.len(),
            txs: self.have_tx.len(),
            presences: self.have_presence.len(),
            requested: self.requested.len(),
            relay_cache_entries: self.relay_cache.len(),
            relay_cache_bytes: self.relay_cache_bytes,
        }
    }
}

impl Default for Inventory {
    fn default() -> Self {
        Self::new()
    }
}

/// Inventory statistics
#[derive(Debug, Clone)]
pub struct InventoryStats {
    pub slices: usize,
    pub txs: usize,
    pub presences: usize,
    pub requested: usize,
    pub relay_cache_entries: usize,
    pub relay_cache_bytes: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn random_hash(seed: u64) -> Hash {
        let mut h = [0u8; 32];
        let bytes = seed.to_le_bytes();
        h[..8].copy_from_slice(&bytes);
        h[8..16].copy_from_slice(&bytes);
        h
    }

    /// Bitcoin Core style: MAX_PEER_REQUEST_IN_FLIGHT = 100 per peer
    ///
    /// Attack scenario: peer sends 10,000 unique inv items
    /// Defense: request() returns false after 100 items from same peer
    ///
    /// Worst case: 125 peers × 100 requests = 12,500 entries = ~1 MB
    #[test]
    fn test_per_peer_request_limit() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        // Try to request 200 items from single peer
        let mut accepted = 0;
        let mut rejected = 0;
        for i in 0..200u64 {
            let item = InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            };
            if inv.request(&item, peer) {
                accepted += 1;
            } else {
                rejected += 1;
            }
        }

        // Only MAX_PEER_REQUEST_IN_FLIGHT accepted
        assert_eq!(accepted, MAX_PEER_REQUEST_IN_FLIGHT);
        assert_eq!(rejected, 100);
        assert_eq!(inv.stats().requested, MAX_PEER_REQUEST_IN_FLIGHT);
        assert_eq!(inv.peer_request_count(&peer), MAX_PEER_REQUEST_IN_FLIGHT);

        println!(
            "accepted: {}, rejected: {}, per-peer count: {}",
            accepted, rejected, inv.peer_request_count(&peer)
        );
    }

    /// Different peers have independent limits
    #[test]
    fn test_per_peer_independent_limits() {
        let mut inv = Inventory::new();
        let peer1: SocketAddr = "127.0.0.1:8333".parse().unwrap();
        let peer2: SocketAddr = "127.0.0.2:8333".parse().unwrap();

        // Fill peer1 to limit
        for i in 0..MAX_PEER_REQUEST_IN_FLIGHT as u64 {
            let item = InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            };
            assert!(inv.request(&item, peer1));
        }

        // peer1 is full
        assert!(!inv.peer_can_request(&peer1));

        // peer2 still has capacity
        assert!(inv.peer_can_request(&peer2));
        let item = InvItem {
            inv_type: InvType::Tx,
            hash: random_hash(1000),
        };
        assert!(inv.request(&item, peer2));
    }

    /// Counter decrements on receive
    #[test]
    fn test_request_counter_decrement() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        // Request 50 items
        for i in 0..50u64 {
            let item = InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            };
            inv.request(&item, peer);
        }
        assert_eq!(inv.peer_request_count(&peer), 50);

        // Receive 20 items
        for i in 0..20u64 {
            inv.received(&random_hash(i));
        }
        assert_eq!(inv.peer_request_count(&peer), 30);

        // Can now request 70 more (30 in-flight + 70 = 100)
        for i in 100..170u64 {
            let item = InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            };
            assert!(inv.request(&item, peer));
        }
        assert_eq!(inv.peer_request_count(&peer), MAX_PEER_REQUEST_IN_FLIGHT);
    }

    /// Dedup protection: should_request() prevents duplicates
    #[test]
    fn test_requested_dedup_protection() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        let item = InvItem {
            inv_type: InvType::Tx,
            hash: random_hash(42),
        };

        // First request OK
        assert!(inv.should_request(&item));
        inv.request(&item, peer);

        // Duplicate blocked (already in requested)
        assert!(!inv.should_request(&item));

        assert_eq!(inv.stats().requested, 1);
    }

    /// already_asked prevents immediate re-request
    #[test]
    fn test_already_asked_protection() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        let item = InvItem {
            inv_type: InvType::Tx,
            hash: random_hash(42),
        };

        // Request and receive
        inv.request(&item, peer);
        inv.received(&item.hash);

        // requested cleared, but already_asked remembers
        assert_eq!(inv.stats().requested, 0);
        assert_eq!(inv.peer_request_count(&peer), 0);

        // Re-request blocked for REQUEST_TIMEOUT_SECS
        assert!(!inv.should_request(&item));
    }

    #[test]
    fn test_request_batch_respects_limit() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        let items: Vec<InvItem> = (0..200u64)
            .map(|i| InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            })
            .collect();

        let requested = inv.request_batch(&items, peer);

        assert_eq!(requested.len(), MAX_PEER_REQUEST_IN_FLIGHT);
        assert_eq!(inv.stats().requested, MAX_PEER_REQUEST_IN_FLIGHT);
        assert_eq!(inv.peer_request_count(&peer), MAX_PEER_REQUEST_IN_FLIGHT);

        for item in &requested {
            assert!(inv.is_requested(&item.hash));
        }
    }

    #[test]
    fn test_request_batch_skips_duplicates() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        let first_item = InvItem {
            inv_type: InvType::Tx,
            hash: random_hash(42),
        };
        assert!(inv.request(&first_item, peer));

        let items: Vec<InvItem> = (40..50u64)
            .map(|i| InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            })
            .collect();

        let requested = inv.request_batch(&items, peer);

        assert_eq!(requested.len(), 9);
        assert!(!requested.iter().any(|i| i.hash == random_hash(42)));
    }

    #[test]
    fn test_request_batch_at_capacity() {
        let mut inv = Inventory::new();
        let peer: SocketAddr = "127.0.0.1:8333".parse().unwrap();

        let fill_items: Vec<InvItem> = (0..MAX_PEER_REQUEST_IN_FLIGHT as u64)
            .map(|i| InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            })
            .collect();
        inv.request_batch(&fill_items, peer);

        let more_items: Vec<InvItem> = (1000..1100u64)
            .map(|i| InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i),
            })
            .collect();
        let requested = inv.request_batch(&more_items, peer);

        assert!(requested.is_empty());
    }

    #[test]
    fn test_lru_hashset_eviction() {
        let mut inv = Inventory::new();

        // Fill have_tx beyond MAX_HAVE_ENTRIES
        for i in 0..MAX_HAVE_ENTRIES + 1000 {
            let item = InvItem {
                inv_type: InvType::Tx,
                hash: random_hash(i as u64),
            };
            inv.add_have(&item);
        }

        // LruHashSet evicts oldest -> bounded
        assert!(inv.stats().txs <= MAX_HAVE_ENTRIES);
        println!("have_tx after overflow: {}", inv.stats().txs);
    }
}
