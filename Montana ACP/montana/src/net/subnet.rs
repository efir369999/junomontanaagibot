// Montana Subnet Reputation Tracker
// Copyright (c) 2024-2026 Alejandro Montana
// Distributed under the MIT software license.

//! Subnet reputation tracking for Eclipse resistance and peer selection.
//!
//! # Purpose
//!
//! Track which /16 subnets have legitimate presence in the network over time.
//! This enables:
//!
//! 1. **Bootstrap diversity verification** — Ensure new nodes connect to peers
//!    from many different subnets, not just attacker-controlled ones.
//!
//! 2. **Long-term Sybil detection** — Subnets that suddenly appear with many
//!    nodes but no history are suspicious.
//!
//! 3. **Peer selection weighting** — Prefer peers from subnets with established
//!    reputation (more unique signers over time = more trustworthy).
//!
//! # Memory Bounds
//!
//! | Collection | Max Size | Calculation |
//! |------------|----------|-------------|
//! | reputations | 65,536 | All possible /16 subnets |
//! | signer_subnets | 50,000 | MAX_TRACKED_SIGNERS constant |
//! | snapshot | 65,536 | Copy of reputations |
//!
//! Total worst-case: ~3 MB (acceptable for full node).
//!
//! # Pruning Strategy
//!
//! `signer_subnets` could grow unbounded (one entry per unique pubkey).
//! To prevent this:
//!
//! 1. **Size limit**: Stop tracking new signers beyond MAX_TRACKED_SIGNERS
//! 2. **Periodic reset**: Clear signer_subnets every τ₃ (2 weeks) during snapshot
//!
//! This means unique_signers counts may be slightly inflated after reset
//! (same pubkey counted again), but this is acceptable for reputation heuristics.
//!
//! # What This Does NOT Protect Against
//!
//! - Attacker with 25+ /16 subnets (cloud providers) — see bootstrap.rs for
//!   additional hardcoded node verification
//! - Attackers who accumulate reputation over years — no perfect solution,
//!   but presence proofs require ongoing cost (AdaptiveCooldown)

use crate::crypto;
use crate::types::{Hash, Subnet16, TAU3_MINUTES, TAU2_MINUTES};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::net::{IpAddr, SocketAddr};

/// Snapshot interval in τ₂ units (every τ₃ = 2016 slices)
pub const REPUTATION_SNAPSHOT_INTERVAL: u64 = TAU3_MINUTES / TAU2_MINUTES;  // 2016

/// Maximum nodes per subnet for bootstrap selection
pub const MAX_NODES_PER_SUBNET: usize = 5;

/// Minimum diverse subnets required for bootstrap (80 peers / 5 per subnet = 16, but we want more)
pub const MIN_DIVERSE_SUBNETS: usize = 25;

/// Subnet reputation entry
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SubnetReputation {
    /// /16 subnet identifier
    pub subnet: Subnet16,
    /// Total accumulated weight from all nodes in this subnet
    pub total_weight: u64,
    /// Number of unique public keys that signed from this subnet
    pub unique_signers: u64,
    /// First τ₂ this subnet appeared
    pub first_seen_tau2: u64,
    /// Last τ₂ this subnet was active
    pub last_seen_tau2: u64,
}

impl SubnetReputation {
    pub fn new(subnet: Subnet16, tau2: u64) -> Self {
        Self {
            subnet,
            total_weight: 0,
            unique_signers: 0,
            first_seen_tau2: tau2,
            last_seen_tau2: tau2,
        }
    }

    /// Add weight from a presence signature
    pub fn add_weight(&mut self, weight: u64, tau2: u64) {
        self.total_weight = self.total_weight.saturating_add(weight);
        self.last_seen_tau2 = tau2;
    }

    /// Register a new unique signer
    pub fn add_signer(&mut self) {
        self.unique_signers = self.unique_signers.saturating_add(1);
    }

    /// Subnet age in τ₂ units
    pub fn age_tau2(&self, current_tau2: u64) -> u64 {
        current_tau2.saturating_sub(self.first_seen_tau2)
    }

    /// Is this a "mature" subnet (> τ₃ old)
    pub fn is_mature(&self, current_tau2: u64) -> bool {
        self.age_tau2(current_tau2) >= REPUTATION_SNAPSHOT_INTERVAL
    }
}

/// Maximum tracked signers before pruning (prevents memory exhaustion)
const MAX_TRACKED_SIGNERS: usize = 50_000;

/// Subnet reputation tracker
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SubnetTracker {
    /// Reputation by subnet
    reputations: HashMap<Subnet16, SubnetReputation>,
    /// Known signers per subnet (pubkey hash -> subnet)
    /// Bounded: cleared every τ₃ or when MAX_TRACKED_SIGNERS reached
    signer_subnets: HashMap<Hash, Subnet16>,
    /// Last snapshot τ₂
    last_snapshot_tau2: u64,
    /// Snapshot reputations (frozen every τ₃)
    snapshot: HashMap<Subnet16, SubnetReputation>,
}

impl SubnetTracker {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a presence signature from an IP
    pub fn record_presence(
        &mut self,
        pubkey: &[u8],
        ip: IpAddr,
        weight: u64,
        tau2: u64,
    ) {
        let subnet = crate::types::ip_to_subnet16(ip);
        let pubkey_hash = crypto::sha3(pubkey);

        // Get or create reputation entry
        let rep = self.reputations
            .entry(subnet)
            .or_insert_with(|| SubnetReputation::new(subnet, tau2));

        // Add weight
        rep.add_weight(weight, tau2);

        // Track unique signers (bounded to prevent memory exhaustion)
        if self.signer_subnets.len() < MAX_TRACKED_SIGNERS {
            if let std::collections::hash_map::Entry::Vacant(e) = self.signer_subnets.entry(pubkey_hash) {
                e.insert(subnet);
                rep.add_signer();
            }
        }
        // Beyond limit: still add weight, skip unique tracking (acceptable approximation)
    }

    /// Get reputation for a subnet
    pub fn get_reputation(&self, subnet: Subnet16) -> Option<&SubnetReputation> {
        self.reputations.get(&subnet)
    }

    /// Get reputation from snapshot (for bootstrap verification)
    pub fn get_snapshot_reputation(&self, subnet: Subnet16) -> Option<&SubnetReputation> {
        self.snapshot.get(&subnet)
    }

    /// Check if snapshot should be taken
    pub fn should_snapshot(&self, current_tau2: u64) -> bool {
        current_tau2.saturating_sub(self.last_snapshot_tau2) >= REPUTATION_SNAPSHOT_INTERVAL
    }

    /// Take snapshot of current reputations
    /// Also clears signer tracking to bound memory
    pub fn take_snapshot(&mut self, current_tau2: u64) {
        self.snapshot = self.reputations.clone();
        self.last_snapshot_tau2 = current_tau2;
        // Reset signer tracking each τ₃ to prevent unbounded growth
        // unique_signers counts remain in reputations (slightly inflated over time, acceptable)
        self.signer_subnets.clear();
    }

    /// Compute Merkle root of all subnet reputations
    pub fn compute_root(&self) -> Hash {
        if self.reputations.is_empty() {
            return [0u8; 32];
        }

        // Sort subnets for deterministic ordering
        let mut subnets: Vec<_> = self.reputations.keys().copied().collect();
        subnets.sort();

        // Build leaves: hash(subnet || total_weight || unique_signers)
        let leaves: Vec<Hash> = subnets
            .iter()
            .map(|subnet| {
                let rep = &self.reputations[subnet];
                let mut data = Vec::with_capacity(18);
                data.extend_from_slice(&subnet.to_le_bytes());
                data.extend_from_slice(&rep.total_weight.to_le_bytes());
                data.extend_from_slice(&rep.unique_signers.to_le_bytes());
                crypto::sha3(&data)
            })
            .collect();

        crypto::merkle_root(&leaves)
    }

    /// Get all reputations sorted by weight (descending)
    pub fn ranked_subnets(&self) -> Vec<(Subnet16, u64)> {
        let mut ranked: Vec<_> = self.reputations
            .iter()
            .map(|(subnet, rep)| (*subnet, rep.total_weight))
            .collect();
        ranked.sort_by(|a, b| b.1.cmp(&a.1));
        ranked
    }

    /// Select peers weighted by subnet reputation with diversity limit
    /// Returns peers grouped by subnet, max `max_per_subnet` per subnet
    pub fn select_diverse_peers(
        &self,
        candidates: &[SocketAddr],
        total_needed: usize,
        max_per_subnet: usize,
    ) -> Vec<SocketAddr> {
        // Group candidates by subnet
        let mut by_subnet: HashMap<Subnet16, Vec<SocketAddr>> = HashMap::new();
        for addr in candidates {
            let subnet = crate::types::ip_to_subnet16(addr.ip());
            by_subnet.entry(subnet).or_default().push(*addr);
        }

        // Get ranked subnets (by reputation)
        let ranked = self.ranked_subnets();

        let mut selected = Vec::with_capacity(total_needed);
        let mut subnet_counts: HashMap<Subnet16, usize> = HashMap::new();

        // First pass: select from high-reputation subnets
        for (subnet, _weight) in &ranked {
            if selected.len() >= total_needed {
                break;
            }

            if let Some(peers) = by_subnet.get(subnet) {
                let count = subnet_counts.entry(*subnet).or_insert(0);
                for peer in peers {
                    if *count >= max_per_subnet {
                        break;
                    }
                    if !selected.contains(peer) {
                        selected.push(*peer);
                        *count += 1;
                        if selected.len() >= total_needed {
                            break;
                        }
                    }
                }
            }
        }

        // Second pass: fill remaining from any subnet (still respecting limit)
        for (subnet, peers) in &by_subnet {
            if selected.len() >= total_needed {
                break;
            }

            let count = subnet_counts.entry(*subnet).or_insert(0);
            for peer in peers {
                if *count >= max_per_subnet {
                    break;
                }
                if !selected.contains(peer) {
                    selected.push(*peer);
                    *count += 1;
                    if selected.len() >= total_needed {
                        break;
                    }
                }
            }
        }

        selected
    }

    /// Count unique subnets in a peer list
    pub fn count_unique_subnets(peers: &[SocketAddr]) -> usize {
        let subnets: std::collections::HashSet<_> = peers
            .iter()
            .map(|addr| crate::types::ip_to_subnet16(addr.ip()))
            .collect();
        subnets.len()
    }

    /// Verify subnet diversity meets minimum requirement
    pub fn verify_diversity(peers: &[SocketAddr]) -> bool {
        Self::count_unique_subnets(peers) >= MIN_DIVERSE_SUBNETS
    }

    /// Get number of tracked subnets
    pub fn len(&self) -> usize {
        self.reputations.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.reputations.is_empty()
    }

    /// Total accumulated weight across all subnets
    pub fn total_weight(&self) -> u64 {
        self.reputations.values().map(|r| r.total_weight).sum()
    }
}

/// Verify subnet reputation root in a slice header
pub fn verify_subnet_root(
    tracker: &SubnetTracker,
    claimed_root: &Hash,
) -> bool {
    let computed = tracker.compute_root();
    &computed == claimed_root
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;

    #[test]
    fn test_subnet_reputation_basic() {
        let mut tracker = SubnetTracker::new();

        // Record from 1.2.x.x subnet
        let ip1 = IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4));
        tracker.record_presence(b"pubkey1", ip1, 100, 0);
        tracker.record_presence(b"pubkey2", ip1, 50, 1);

        // Record from 10.20.x.x subnet
        let ip2 = IpAddr::V4(Ipv4Addr::new(10, 20, 30, 40));
        tracker.record_presence(b"pubkey3", ip2, 200, 2);

        assert_eq!(tracker.len(), 2);

        let subnet1 = crate::types::ip_to_subnet16(ip1);
        let rep1 = tracker.get_reputation(subnet1).unwrap();
        assert_eq!(rep1.total_weight, 150);
        assert_eq!(rep1.unique_signers, 2);

        let subnet2 = crate::types::ip_to_subnet16(ip2);
        let rep2 = tracker.get_reputation(subnet2).unwrap();
        assert_eq!(rep2.total_weight, 200);
        assert_eq!(rep2.unique_signers, 1);
    }

    #[test]
    fn test_merkle_root_deterministic() {
        let mut tracker = SubnetTracker::new();

        let ip1 = IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4));
        let ip2 = IpAddr::V4(Ipv4Addr::new(10, 20, 30, 40));

        tracker.record_presence(b"pubkey1", ip1, 100, 0);
        tracker.record_presence(b"pubkey2", ip2, 200, 1);

        let root1 = tracker.compute_root();
        let root2 = tracker.compute_root();

        assert_eq!(root1, root2);
        assert_ne!(root1, [0u8; 32]);
    }

    #[test]
    fn test_diverse_peer_selection() {
        let mut tracker = SubnetTracker::new();

        // Build reputation for different subnets
        for i in 0u8..50 {
            let ip = IpAddr::V4(Ipv4Addr::new(i, i, 1, 1));
            tracker.record_presence(&[i], ip, (50 - i) as u64 * 100, 0);
        }

        // Create candidates from various subnets
        let mut candidates = Vec::new();
        for i in 0u8..50 {
            for j in 0u8..10 {
                let addr: SocketAddr = format!("{}.{}.{}.{}:19333", i, i, j, j).parse().unwrap();
                candidates.push(addr);
            }
        }

        // Select 80 peers with max 5 per subnet
        let selected = tracker.select_diverse_peers(&candidates, 80, 5);

        assert_eq!(selected.len(), 80);

        // Verify diversity
        let unique_subnets = SubnetTracker::count_unique_subnets(&selected);
        assert!(unique_subnets >= 16); // 80 / 5 = 16 minimum
    }

    #[test]
    fn test_subnet_limit_enforced() {
        let tracker = SubnetTracker::new();

        // All candidates from same subnet
        let candidates: Vec<SocketAddr> = (0..100)
            .map(|i| format!("1.2.{}.{}:19333", i % 256, i / 256).parse().unwrap())
            .collect();

        // Select with limit 5
        let selected = tracker.select_diverse_peers(&candidates, 80, 5);

        // Should only get 5 (limit per subnet)
        assert_eq!(selected.len(), 5);
    }

    #[test]
    fn test_snapshot() {
        let mut tracker = SubnetTracker::new();

        let ip = IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4));
        tracker.record_presence(b"pubkey1", ip, 100, 0);

        // Take snapshot
        tracker.take_snapshot(0);

        // Add more
        tracker.record_presence(b"pubkey2", ip, 50, 1);

        // Live shows 150
        let subnet = crate::types::ip_to_subnet16(ip);
        assert_eq!(tracker.get_reputation(subnet).unwrap().total_weight, 150);

        // Snapshot shows 100
        assert_eq!(tracker.get_snapshot_reputation(subnet).unwrap().total_weight, 100);
    }
}
