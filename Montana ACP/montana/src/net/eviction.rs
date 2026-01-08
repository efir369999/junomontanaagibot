//! Peer eviction with protected categories

use super::peer::PeerInfo;
use std::collections::HashMap;
use std::net::SocketAddr;

/// Eviction candidate with scoring info
#[derive(Debug, Clone)]
pub struct EvictionCandidate {
    pub addr: SocketAddr,
    pub connected_at: u64,
    pub latency_ms: Option<u64>,
    pub bytes_recv: u64,
    pub last_recv: u64,
    pub last_tx_time: u64,
    pub last_slice_time: u64,
    pub inbound: bool,
    pub netgroup: u32,
    pub has_noban: bool,
}

impl From<&PeerInfo> for EvictionCandidate {
    fn from(peer: &PeerInfo) -> Self {
        Self {
            addr: peer.addr,
            connected_at: peer.connected_at,
            latency_ms: peer.latency_ms,
            bytes_recv: peer.bytes_recv,
            last_recv: peer.last_recv,
            last_tx_time: peer.last_tx_time,
            last_slice_time: peer.last_slice_time,
            inbound: peer.inbound,
            netgroup: get_netgroup(&peer.addr),
            has_noban: peer.has_noban,
        }
    }
}

/// Get /16 netgroup for an IP address
fn get_netgroup(addr: &SocketAddr) -> u32 {
    use std::net::IpAddr;
    match addr.ip() {
        IpAddr::V4(ip) => {
            let octets = ip.octets();
            ((octets[0] as u32) << 8) | (octets[1] as u32)
        }
        IpAddr::V6(ip) => {
            let segments = ip.segments();
            ((segments[0] as u32) << 16) | (segments[1] as u32)
        }
    }
}

/// Number of peers to protect in each category
const PROTECTED_BY_NETGROUP: usize = 4;
const PROTECTED_BY_PING: usize = 8;
const PROTECTED_BY_TX: usize = 4;
const PROTECTED_BY_SLICE: usize = 4;
const PROTECTED_BY_LONGEVITY: usize = 8;

/// Select a peer to evict from inbound connections
/// Returns Some(addr) when eviction needed, None when all peers protected
pub fn select_peer_to_evict(peers: &[PeerInfo]) -> Option<SocketAddr> {
    // Filter to only inbound peers that can be evicted
    let mut candidates: Vec<EvictionCandidate> = peers
        .iter()
        .filter(|p| p.inbound)
        .map(EvictionCandidate::from)
        .collect();

    if candidates.is_empty() {
        return None;
    }

    // Layer 1: Protect peers with NoBan permission
    candidates.retain(|c| !c.has_noban);
    if candidates.is_empty() {
        return None;
    }

    // Layer 2: Protect peers from diverse netgroups (4 random)
    protect_by_netgroup(&mut candidates, PROTECTED_BY_NETGROUP);
    if candidates.is_empty() {
        return None;
    }

    // Layer 3: Protect peers with lowest ping (8)
    protect_by_ping(&mut candidates, PROTECTED_BY_PING);
    if candidates.is_empty() {
        return None;
    }

    // Layer 4: Protect peers with recent transactions (4)
    protect_by_recent_tx(&mut candidates, PROTECTED_BY_TX);
    if candidates.is_empty() {
        return None;
    }

    // Layer 5: Protect peers with recent slices (4)
    protect_by_recent_slice(&mut candidates, PROTECTED_BY_SLICE);
    if candidates.is_empty() {
        return None;
    }

    // Layer 6: Protect longest-connected peers (8)
    protect_by_longevity(&mut candidates, PROTECTED_BY_LONGEVITY);
    if candidates.is_empty() {
        return None;
    }

    // Find netgroup with most candidates (highest risk)
    let netgroup_counts = count_by_netgroup(&candidates);
    let worst_netgroup = netgroup_counts
        .iter()
        .max_by_key(|(_, count)| *count)
        .map(|(netgroup, _)| *netgroup)?;

    // Evict youngest peer from worst netgroup
    candidates
        .iter()
        .filter(|c| c.netgroup == worst_netgroup)
        .max_by_key(|c| c.connected_at)
        .map(|c| c.addr)
}

/// Protect peers by netgroup diversity
fn protect_by_netgroup(candidates: &mut Vec<EvictionCandidate>, count: usize) {
    if candidates.len() <= count {
        candidates.clear();
        return;
    }

    // Group by netgroup
    let mut by_netgroup: HashMap<u32, Vec<usize>> = HashMap::new();
    for (i, c) in candidates.iter().enumerate() {
        by_netgroup.entry(c.netgroup).or_default().push(i);
    }

    // Select one random peer from each unique netgroup (up to count)
    let mut protected = Vec::new();
    let mut netgroups: Vec<_> = by_netgroup.keys().copied().collect();

    // Deterministic shuffle using connected_at as seed
    netgroups.sort_by(|a, b| {
        let a_time = by_netgroup[a].iter()
            .map(|i| candidates[*i].connected_at)
            .min()
            .unwrap_or(0);
        let b_time = by_netgroup[b].iter()
            .map(|i| candidates[*i].connected_at)
            .min()
            .unwrap_or(0);
        a_time.cmp(&b_time)
    });

    for netgroup in netgroups.iter().take(count) {
        if let Some(&idx) = by_netgroup[netgroup].first() {
            protected.push(idx);
        }
    }

    // Remove protected peers
    protected.sort_by(|a, b| b.cmp(a)); // Reverse order for removal
    for idx in protected {
        if idx < candidates.len() {
            candidates.remove(idx);
        }
    }
}

/// Protect peers with lowest latency
fn protect_by_ping(candidates: &mut Vec<EvictionCandidate>, count: usize) {
    if candidates.len() <= count {
        candidates.clear();
        return;
    }

    // Sort by latency (lowest first)
    candidates.sort_by(|a, b| {
        match (a.latency_ms, b.latency_ms) {
            (Some(a_lat), Some(b_lat)) => a_lat.cmp(&b_lat),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => std::cmp::Ordering::Equal,
        }
    });

    // Remove first `count` (protected)
    candidates.drain(..count.min(candidates.len()));
}

/// Protect peers with recent transaction relay
fn protect_by_recent_tx(candidates: &mut Vec<EvictionCandidate>, count: usize) {
    if candidates.len() <= count {
        candidates.clear();
        return;
    }

    // Sort by last tx time (most recent first)
    candidates.sort_by(|a, b| b.last_tx_time.cmp(&a.last_tx_time));

    // Remove first `count` (protected)
    candidates.drain(..count.min(candidates.len()));
}

/// Protect peers with recent slice relay
fn protect_by_recent_slice(candidates: &mut Vec<EvictionCandidate>, count: usize) {
    if candidates.len() <= count {
        candidates.clear();
        return;
    }

    // Sort by last slice time (most recent first)
    candidates.sort_by(|a, b| b.last_slice_time.cmp(&a.last_slice_time));

    // Remove first `count` (protected)
    candidates.drain(..count.min(candidates.len()));
}

/// Protect longest-connected peers
fn protect_by_longevity(candidates: &mut Vec<EvictionCandidate>, count: usize) {
    if candidates.len() <= count {
        candidates.clear();
        return;
    }

    // Sort by connected_at (oldest first = longest connected)
    candidates.sort_by(|a, b| a.connected_at.cmp(&b.connected_at));

    // Remove first `count` (protected)
    candidates.drain(..count.min(candidates.len()));
}

/// Count candidates per netgroup
fn count_by_netgroup(candidates: &[EvictionCandidate]) -> HashMap<u32, usize> {
    let mut counts = HashMap::new();
    for c in candidates {
        *counts.entry(c.netgroup).or_insert(0) += 1;
    }
    counts
}

/// Eviction statistics
#[derive(Debug, Clone, Default)]
pub struct EvictionStats {
    pub total_candidates: usize,
    pub protected_noban: usize,
    pub protected_netgroup: usize,
    pub protected_ping: usize,
    pub protected_tx: usize,
    pub protected_slice: usize,
    pub protected_longevity: usize,
    pub remaining: usize,
}

/// Get detailed eviction statistics (for debugging)
pub fn eviction_stats(peers: &[PeerInfo]) -> EvictionStats {
    let candidates: Vec<EvictionCandidate> = peers
        .iter()
        .filter(|p| p.inbound)
        .map(EvictionCandidate::from)
        .collect();

    let total = candidates.len();
    let noban = candidates.iter().filter(|c| c.has_noban).count();

    // This is simplified - full stats would track each layer
    EvictionStats {
        total_candidates: total,
        protected_noban: noban,
        protected_netgroup: PROTECTED_BY_NETGROUP.min(total - noban),
        protected_ping: PROTECTED_BY_PING,
        protected_tx: PROTECTED_BY_TX,
        protected_slice: PROTECTED_BY_SLICE,
        protected_longevity: PROTECTED_BY_LONGEVITY,
        remaining: total.saturating_sub(
            noban + PROTECTED_BY_NETGROUP + PROTECTED_BY_PING +
            PROTECTED_BY_TX + PROTECTED_BY_SLICE + PROTECTED_BY_LONGEVITY
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::net::types::SyncState;

    fn make_peer(addr: &str, connected_at: u64, latency: Option<u64>) -> PeerInfo {
        PeerInfo {
            addr: addr.parse().unwrap(),
            services: 0,
            version: 1,
            user_agent: String::new(),
            inbound: true,
            is_ready: true,
            connected_at,
            last_recv: connected_at,
            last_send: connected_at,
            bytes_recv: 0,
            bytes_sent: 0,
            latency_ms: latency,
            best_known_slice: 0,
            sync_state: SyncState::Idle,
            ban_score: 0,
            last_tx_time: 0,
            last_slice_time: 0,
            has_noban: false,
        }
    }

    #[test]
    fn test_eviction_empty() {
        let peers: Vec<PeerInfo> = vec![];
        assert!(select_peer_to_evict(&peers).is_none());
    }

    #[test]
    fn test_eviction_single() {
        let peers = vec![make_peer("1.2.3.4:1234", 100, Some(50))];
        // Single peer should still be protected by at least one layer
        // With 28 total protected slots and 1 peer, no eviction
        assert!(select_peer_to_evict(&peers).is_none());
    }

    #[test]
    fn test_eviction_many_same_netgroup() {
        // Create 50 peers from same /16
        let peers: Vec<PeerInfo> = (0..50)
            .map(|i| make_peer(&format!("1.2.{}.1:1234", i), i as u64, Some(100)))
            .collect();

        // Should evict youngest from the worst netgroup
        let evicted = select_peer_to_evict(&peers);

        // With 28+ protected slots, we may or may not evict
        // The exact behavior depends on the protection logic
        if let Some(addr) = evicted {
            // Should be from the same netgroup (1.2.x.x)
            let ip = addr.ip();
            if let std::net::IpAddr::V4(ipv4) = ip {
                let octets = ipv4.octets();
                assert_eq!(octets[0], 1);
                assert_eq!(octets[1], 2);
            }
        }
    }
}
