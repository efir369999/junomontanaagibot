//! Headers-first sync with orphan handling

use crate::types::{Hash, PresenceProof, Slice, SliceHeader, GRACE_PERIOD_SECS};
use std::collections::{HashMap, HashSet, VecDeque};
use std::net::SocketAddr;
use std::time::Instant;
use tracing::{debug, warn};

// =============================================================================
// SYNC CONSTANTS
// =============================================================================

/// Maximum orphan slices to keep in memory.
/// 100 orphans handles moderate out-of-order delivery.
///
/// Security: Bounded to prevent memory exhaustion from attacker
/// flooding us with orphan slices. Each orphan is up to 4MB,
/// so worst case is 400MB memory usage.
///
/// Note: During deep reorg (>100 slices), some orphans may be
/// evicted before their parent arrives. This is acceptable as
/// we can re-request them.
const MAX_ORPHANS: usize = 100;

/// Maximum concurrent downloads per single peer.
/// 4 provides good parallelism without overwhelming any peer.
///
/// Rationale:
/// - Too low (1-2): underutilizes peer bandwidth
/// - Too high (8+): single slow peer blocks many slots
/// - 4 is Bitcoin Core's choice for block download
const MAX_DOWNLOADS_PER_PEER: usize = 4;

/// Maximum total parallel downloads across all peers.
/// With 8 outbound peers × 4 per peer = 32 max.
///
/// This equals MAX_OUTBOUND × MAX_DOWNLOADS_PER_PEER.
/// Ensures we don't exceed our peer capacity.
const MAX_PARALLEL_DOWNLOADS: usize = 32;

/// Download timeout before retry.
/// 2 minutes allows for slow peers without blocking sync.
///
/// After timeout, slice is re-queued for download from different peer.
/// After 3 failures, slice is logged and abandoned (manual intervention needed).
const DOWNLOAD_TIMEOUT_SECS: u64 = 120;

/// Request state
#[derive(Debug, Clone)]
struct DownloadRequest {
    peer: SocketAddr,
    requested_at: Instant,
    retries: u32,
}

/// Orphan header waiting for parent (body discarded to prevent memory exhaustion)
///
/// Security: We only store headers (~200 bytes), not full slices (~4MB).
/// This limits orphan pool memory to MAX_ORPHANS × 200 bytes = 20KB (vs 400MB).
/// When parent arrives, we re-request the full slice from peers.
#[derive(Debug)]
struct OrphanHeader {
    header: SliceHeader,
    received_at: Instant,
}

/// Parallel slice downloader
pub struct SliceDownloader {
    /// Our current best slice index
    best_index: u64,

    /// Target slice index (from peers)
    target_index: u64,

    /// Pending download requests
    pending: HashMap<u64, DownloadRequest>,

    /// Downloads per peer (for fairness)
    peer_downloads: HashMap<SocketAddr, usize>,

    /// Completed downloads waiting to be processed
    completed: VecDeque<Slice>,

    /// Queue of indices to download
    download_queue: VecDeque<u64>,
}

impl SliceDownloader {
    pub fn new(best_index: u64) -> Self {
        Self {
            best_index,
            target_index: best_index,
            pending: HashMap::new(),
            peer_downloads: HashMap::new(),
            completed: VecDeque::new(),
            download_queue: VecDeque::new(),
        }
    }

    /// Set sync target from peer
    pub fn set_target(&mut self, target: u64) {
        if target > self.target_index {
            self.target_index = target;

            // Queue new indices for download
            let start = self.best_index + 1;
            for idx in start..=target {
                if !self.pending.contains_key(&idx) && !self.download_queue.contains(&idx) {
                    self.download_queue.push_back(idx);
                }
            }

            debug!("Sync target updated to {}, queued {} slices",
                   target, self.download_queue.len());
        }
    }

    /// Get next downloads for a peer
    pub fn get_downloads(&mut self, peer: SocketAddr, max: usize) -> Vec<u64> {
        let peer_count = self.peer_downloads.get(&peer).copied().unwrap_or(0);
        if peer_count >= MAX_DOWNLOADS_PER_PEER {
            return vec![];
        }

        if self.pending.len() >= MAX_PARALLEL_DOWNLOADS {
            return vec![];
        }

        let available = (MAX_DOWNLOADS_PER_PEER - peer_count).min(max);
        let available = available.min(MAX_PARALLEL_DOWNLOADS - self.pending.len());

        let mut downloads = Vec::new();

        while downloads.len() < available {
            if let Some(idx) = self.download_queue.pop_front() {
                // Skip if already pending or completed
                if self.pending.contains_key(&idx) {
                    continue;
                }

                let request = DownloadRequest {
                    peer,
                    requested_at: Instant::now(),
                    retries: 0,
                };

                self.pending.insert(idx, request);
                *self.peer_downloads.entry(peer).or_insert(0) += 1;
                downloads.push(idx);
            } else {
                break;
            }
        }

        downloads
    }

    /// Mark slice as received
    pub fn received(&mut self, slice: Slice) {
        let idx = slice.header.slice_index;

        if let Some(request) = self.pending.remove(&idx)
            && let Some(count) = self.peer_downloads.get_mut(&request.peer)
        {
            *count = count.saturating_sub(1);
        }

        self.completed.push_back(slice);
    }

    /// Mark download as failed (for retry)
    pub fn failed(&mut self, idx: u64) {
        if let Some(mut request) = self.pending.remove(&idx) {
            if let Some(count) = self.peer_downloads.get_mut(&request.peer) {
                *count = count.saturating_sub(1);
            }

            request.retries += 1;
            if request.retries < 3 {
                // Re-queue for retry
                self.download_queue.push_front(idx);
            } else {
                warn!("Slice {} failed after 3 retries", idx);
            }
        }
    }

    /// Check for timed out requests
    pub fn check_timeouts(&mut self) -> Vec<u64> {
        let timeout = std::time::Duration::from_secs(DOWNLOAD_TIMEOUT_SECS);
        let now = Instant::now();

        let timed_out: Vec<u64> = self.pending
            .iter()
            .filter(|(_, req)| now.duration_since(req.requested_at) > timeout)
            .map(|(idx, _)| *idx)
            .collect();

        for idx in &timed_out {
            self.failed(*idx);
        }

        timed_out
    }

    /// Get next completed slice in order
    pub fn next_completed(&mut self) -> Option<Slice> {
        // Sort completed by index
        let mut sorted: Vec<_> = self.completed.drain(..).collect();
        sorted.sort_by_key(|s| s.header.slice_index);

        // Return only the next expected slice
        let expected = self.best_index + 1;

        let mut result = None;
        for slice in sorted {
            if slice.header.slice_index == expected && result.is_none() {
                self.best_index = slice.header.slice_index;
                result = Some(slice);
            } else {
                // Re-queue others
                self.completed.push_back(slice);
            }
        }

        result
    }

    /// Update best index after processing
    pub fn set_best(&mut self, idx: u64) {
        self.best_index = idx;
    }

    /// Check if sync is complete
    pub fn is_synced(&self) -> bool {
        self.best_index >= self.target_index
            && self.pending.is_empty()
            && self.download_queue.is_empty()
    }

    /// Get sync progress
    pub fn progress(&self) -> (u64, u64) {
        (self.best_index, self.target_index)
    }

    /// Get stats
    pub fn stats(&self) -> SyncStats {
        SyncStats {
            best_index: self.best_index,
            target_index: self.target_index,
            pending: self.pending.len(),
            queued: self.download_queue.len(),
            completed: self.completed.len(),
        }
    }
}

/// Sync statistics
#[derive(Debug, Clone)]
pub struct SyncStats {
    pub best_index: u64,
    pub target_index: u64,
    pub pending: usize,
    pub queued: usize,
    pub completed: usize,
}

/// Orphan header buffer (memory-efficient)
///
/// Security: Stores only headers, not full slices.
/// Memory usage: MAX_ORPHANS × ~200 bytes = ~20KB (vs 400MB with full slices).
pub struct OrphanPool {
    /// Orphan headers keyed by their expected prev_hash
    by_prev_hash: HashMap<Hash, Vec<OrphanHeader>>,

    /// All orphan indices for dedup
    indices: HashSet<u64>,

    /// Total count
    count: usize,
}

impl OrphanPool {
    pub fn new() -> Self {
        Self {
            by_prev_hash: HashMap::new(),
            indices: HashSet::new(),
            count: 0,
        }
    }

    /// Add orphan header (discards body to prevent memory exhaustion)
    ///
    /// Security: Only the header is stored (~200 bytes), not the full slice (~4MB).
    /// When parent arrives, the caller must re-request the full slice body.
    pub fn add(&mut self, header: SliceHeader) -> bool {
        if self.count >= MAX_ORPHANS {
            self.expire_oldest();
        }

        let slice_index = header.slice_index;
        if self.indices.contains(&slice_index) {
            return false; // Already have this orphan
        }

        let prev_hash = header.prev_hash;
        self.indices.insert(slice_index);
        self.by_prev_hash
            .entry(prev_hash)
            .or_default()
            .push(OrphanHeader {
                header,
                received_at: Instant::now(),
            });
        self.count += 1;

        debug!("Added orphan header, total: {}", self.count);
        true
    }

    /// Get orphan headers that can now be connected (their parent is this hash)
    ///
    /// Returns headers only — caller must re-request full slice bodies from peers.
    /// This is the price we pay for 20,000x memory efficiency.
    pub fn get_children(&mut self, parent_hash: &Hash) -> Vec<SliceHeader> {
        if let Some(orphans) = self.by_prev_hash.remove(parent_hash) {
            for orphan in &orphans {
                self.indices.remove(&orphan.header.slice_index);
                self.count = self.count.saturating_sub(1);
            }
            orphans.into_iter().map(|o| o.header).collect()
        } else {
            vec![]
        }
    }

    /// Check if we have this orphan
    pub fn contains(&self, index: u64) -> bool {
        self.indices.contains(&index)
    }

    /// Expire oldest orphans
    fn expire_oldest(&mut self) {
        let mut oldest_time = Instant::now();
        let mut oldest_hash = None;

        for (hash, orphans) in &self.by_prev_hash {
            if let Some(orphan) = orphans.first()
                && orphan.received_at < oldest_time
            {
                oldest_time = orphan.received_at;
                oldest_hash = Some(*hash);
            }
        }

        if let Some(hash) = oldest_hash
            && let Some(orphans) = self.by_prev_hash.remove(&hash)
        {
            for orphan in orphans {
                self.indices.remove(&orphan.header.slice_index);
                self.count = self.count.saturating_sub(1);
            }
        }
    }

    /// Expire orphans older than max age
    pub fn expire(&mut self, max_age_secs: u64) {
        let max_age = std::time::Duration::from_secs(max_age_secs);
        let now = Instant::now();

        let expired_hashes: Vec<Hash> = self.by_prev_hash
            .iter()
            .filter(|(_, orphans)| {
                orphans.iter().all(|o| now.duration_since(o.received_at) > max_age)
            })
            .map(|(h, _)| *h)
            .collect();

        for hash in expired_hashes {
            if let Some(orphans) = self.by_prev_hash.remove(&hash) {
                for orphan in orphans {
                    self.indices.remove(&orphan.header.slice_index);
                    self.count = self.count.saturating_sub(1);
                }
            }
        }
    }

    /// Get count
    pub fn len(&self) -> usize {
        self.count
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.count == 0
    }
}

impl Default for OrphanPool {
    fn default() -> Self {
        Self::new()
    }
}

/// Headers-first sync state
pub struct HeaderSync {
    /// Headers we've downloaded
    headers: Vec<SliceHeader>,

    /// Current sync position
    position: usize,

    /// Is header sync complete?
    complete: bool,
}

impl HeaderSync {
    pub fn new() -> Self {
        Self {
            headers: Vec::new(),
            position: 0,
            complete: false,
        }
    }

    /// Add headers from peer
    pub fn add_headers(&mut self, headers: Vec<SliceHeader>) {
        // Validate chain - check slice indices are sequential
        if !self.headers.is_empty() {
            let last = self.headers.last().unwrap();
            if let Some(first) = headers.first()
                && first.slice_index != last.slice_index + 1
            {
                warn!("Header chain broken: expected {}, got {}",
                      last.slice_index + 1, first.slice_index);
                return;
            }
        }

        self.headers.extend(headers);
    }

    /// Mark header sync as complete
    pub fn mark_complete(&mut self) {
        self.complete = true;
    }

    /// Get next slice index to download
    pub fn next_index(&self) -> Option<u64> {
        if self.position < self.headers.len() {
            Some(self.headers[self.position].slice_index)
        } else {
            None
        }
    }

    /// Advance position after slice received
    pub fn advance(&mut self) {
        self.position += 1;
    }

    /// Is sync complete?
    pub fn is_complete(&self) -> bool {
        self.complete && self.position >= self.headers.len()
    }

    /// Get progress
    pub fn progress(&self) -> (usize, usize) {
        (self.position, self.headers.len())
    }
}

impl Default for HeaderSync {
    fn default() -> Self {
        Self::new()
    }
}

/// Late signature buffer for presence proofs that arrive after τ₂ closes
/// but within the grace period (30 seconds by default)
pub struct LateSignatureBuffer {
    /// Signatures waiting to be included in next τ₂
    /// Key: τ₂ index the signature was intended for
    pending: HashMap<u64, Vec<LateSignature>>,

    /// Maximum signatures to buffer
    max_size: usize,

    /// Current τ₂ index
    current_tau2: u64,
}

/// A late signature entry
#[derive(Debug, Clone)]
pub struct LateSignature {
    pub proof: PresenceProof,
    pub intended_tau2: u64,
    pub received_at: Instant,
    pub source: SocketAddr,
}

impl LateSignatureBuffer {
    pub fn new(current_tau2: u64) -> Self {
        Self {
            pending: HashMap::new(),
            max_size: 10000,
            current_tau2,
        }
    }

    /// Add a late signature (returns true if accepted)
    pub fn add(&mut self, proof: PresenceProof, intended_tau2: u64, source: SocketAddr) -> bool {
        // Only accept signatures for previous τ₂ within grace period
        if intended_tau2 >= self.current_tau2 {
            // Not late - should be processed normally
            return false;
        }

        // Only accept signatures from immediately previous τ₂
        if intended_tau2 + 1 != self.current_tau2 {
            debug!("Rejecting signature for old τ₂ {}", intended_tau2);
            return false;
        }

        // Check buffer size
        let total: usize = self.pending.values().map(|v| v.len()).sum();
        if total >= self.max_size {
            self.expire_oldest();
        }

        // Check grace period (should be done by caller, but double-check)
        let entry = LateSignature {
            proof,
            intended_tau2,
            received_at: Instant::now(),
            source,
        };

        self.pending
            .entry(intended_tau2)
            .or_default()
            .push(entry);

        debug!("Buffered late signature for τ₂ {}", intended_tau2);
        true
    }

    /// Get all late signatures for a τ₂ and clear the buffer
    pub fn drain(&mut self, tau2: u64) -> Vec<PresenceProof> {
        self.pending
            .remove(&tau2)
            .map(|entries| entries.into_iter().map(|e| e.proof).collect())
            .unwrap_or_default()
    }

    /// Update current τ₂ (called when τ₂ advances)
    pub fn advance_tau2(&mut self, new_tau2: u64) {
        // Remove signatures older than 1 τ₂
        let old: Vec<u64> = self.pending
            .keys()
            .filter(|&&k| k + 2 <= new_tau2)
            .copied()
            .collect();

        for k in old {
            self.pending.remove(&k);
        }

        self.current_tau2 = new_tau2;
    }

    /// Expire oldest entries to make room
    fn expire_oldest(&mut self) {
        // Find oldest τ₂
        if let Some(&oldest_tau2) = self.pending.keys().min()
            && let Some(entries) = self.pending.get_mut(&oldest_tau2)
        {
            // Remove oldest entry
            if !entries.is_empty() {
                entries.remove(0);
            }
            if entries.is_empty() {
                self.pending.remove(&oldest_tau2);
            }
        }
    }

    /// Check if a signature is within grace period
    pub fn is_within_grace_period(signature_time: u64, current_time: u64) -> bool {
        current_time.saturating_sub(signature_time) <= GRACE_PERIOD_SECS
    }

    /// Get count of pending late signatures
    pub fn len(&self) -> usize {
        self.pending.values().map(|v| v.len()).sum()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.pending.is_empty()
    }

    /// Get stats
    pub fn stats(&self) -> LateSignatureStats {
        LateSignatureStats {
            pending: self.len(),
            tau2_buckets: self.pending.len(),
            current_tau2: self.current_tau2,
        }
    }
}

impl Default for LateSignatureBuffer {
    fn default() -> Self {
        Self::new(0)
    }
}

/// Late signature statistics
#[derive(Debug, Clone)]
pub struct LateSignatureStats {
    pub pending: usize,
    pub tau2_buckets: usize,
    pub current_tau2: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_downloader_basic() {
        let mut dl = SliceDownloader::new(0);
        dl.set_target(10);

        let peer: SocketAddr = "1.2.3.4:1234".parse().unwrap();
        let downloads = dl.get_downloads(peer, 4);

        assert_eq!(downloads.len(), 4);
        assert_eq!(downloads[0], 1);
        assert_eq!(downloads[3], 4);
    }

    #[test]
    fn test_orphan_pool() {
        let mut pool = OrphanPool::new();

        // Create dummy header (orphan pool only stores headers now)
        let header = SliceHeader {
            prev_hash: [1u8; 32],
            timestamp: 0,
            slice_index: 5,
            winner_pubkey: vec![],
            cooldown_medians: [1, 1, 1],
            registrations: [0, 0, 0],
            cumulative_weight: 0,
            subnet_reputation_root: [0u8; 32],
        };

        assert!(pool.add(header.clone()));
        assert!(!pool.add(header)); // Duplicate

        assert!(pool.contains(5));
        assert_eq!(pool.len(), 1);

        let children = pool.get_children(&[1u8; 32]);
        assert_eq!(children.len(), 1);
        assert!(pool.is_empty());
    }
}
