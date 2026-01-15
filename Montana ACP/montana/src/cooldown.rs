//! Adaptive cooldown — median-based, per-tier, rate-limited

use crate::types::{
    MedianSnapshot, NodeType,
    COOLDOWN_DEFAULT_TAU2, COOLDOWN_MAX_TAU2, COOLDOWN_MIN_TAU2, COOLDOWN_WINDOW_TAU2,
    COOLDOWN_SMOOTH_WINDOWS, COOLDOWN_MAX_CHANGE_PERCENT,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Adaptive cooldown calculator
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AdaptiveCooldown {
    /// Median snapshots per tier (0=Full, 1=Light, 2=Client)
    pub snapshots: [MedianSnapshot; 3],
    /// Registration history per τ₂ per tier (for median calculation)
    /// Kept for 4 τ₃ (56 days) for smoothing
    registrations: HashMap<(u64, u8), u64>,  // (tau2, tier) -> count
    /// Historical medians per τ₃ window per tier (for 4 τ₃ smoothing)
    /// Each entry is (τ₃_index, median)
    median_history: HashMap<(u64, u8), u64>,  // (tau3_index, tier) -> median
    /// Previous effective cooldown per tier (for rate limiting)
    previous_cooldown: [u64; 3],
}

impl AdaptiveCooldown {
    pub fn new() -> Self {
        Self {
            snapshots: [
                MedianSnapshot::default(),
                MedianSnapshot::default(),
                MedianSnapshot::default(),
            ],
            registrations: HashMap::new(),
            median_history: HashMap::new(),
            previous_cooldown: [COOLDOWN_DEFAULT_TAU2; 3],
        }
    }

    /// Record a new registration
    pub fn record_registration(&mut self, tau2: u64, node_type: NodeType) {
        let tier = node_type.tier_index();
        let key = (tau2, tier);
        *self.registrations.entry(key).or_insert(0) += 1;
    }

    /// Calculate smoothed median using 4 τ₃ (56 days) sliding average
    ///
    /// Spreads sudden registration spikes over time, making manipulation expensive.
    fn smoothed_median(&self, current_tau2: u64, tier: u8) -> u64 {
        let current_tau3 = current_tau2 / COOLDOWN_WINDOW_TAU2;

        let mut medians = Vec::new();
        for i in 0..COOLDOWN_SMOOTH_WINDOWS {
            let tau3_idx = current_tau3.saturating_sub(i);
            if let Some(&median) = self.median_history.get(&(tau3_idx, tier)) {
                if median > 0 {
                    medians.push(median);
                }
            }
        }

        let current_median = self.snapshots[tier as usize].median;
        if current_median > 0 {
            medians.push(current_median);
        }

        if medians.is_empty() {
            return 0;
        }

        let sum: u64 = medians.iter().sum();
        sum / medians.len() as u64
    }

    /// Apply rate limit: cooldown changes by maximum 20% per τ₃
    fn rate_limited_cooldown(&self, raw_cooldown: u64, tier: usize) -> u64 {
        let previous = self.previous_cooldown[tier];
        if previous == 0 {
            return raw_cooldown;
        }

        let max_change = (previous * COOLDOWN_MAX_CHANGE_PERCENT) / 100;
        let max_change = max_change.max(COOLDOWN_MIN_TAU2);

        if raw_cooldown > previous {
            raw_cooldown.min(previous.saturating_add(max_change))
        } else {
            raw_cooldown.max(previous.saturating_sub(max_change))
        }
    }

    /// Calculate cooldown for a new node at current τ₂
    ///
    /// Uses smoothed median (4 τ₃ average) and rate limiting (±20% per τ₃)
    ///
    /// Formula: Linear interpolation based on registration rate
    /// - Below smoothed median: cooldown = MIN (1 day) to MID (7 days)
    /// - At smoothed median: cooldown = τ₃ / 2 (7 days)
    /// - Above smoothed median: linear scale up to MAX (180 days)
    pub fn calculate_cooldown(&self, current_tau2: u64, node_type: NodeType) -> u64 {
        let tier = node_type.tier_index();
        let tier_idx = tier as usize;
        let snapshot = &self.snapshots[tier_idx];

        if snapshot.counts_per_tau2.is_empty() {
            return COOLDOWN_DEFAULT_TAU2;
        }

        let median = self.smoothed_median(current_tau2, tier);
        if median == 0 {
            return COOLDOWN_DEFAULT_TAU2;
        }

        let current_count = self
            .registrations
            .get(&(current_tau2, tier))
            .copied()
            .unwrap_or(0);

        let ratio = current_count as f64 / median as f64;
        let mid_cooldown = COOLDOWN_WINDOW_TAU2 / 2;

        let raw_cooldown = if ratio <= 1.0 {
            let scaled = COOLDOWN_MIN_TAU2 as f64 + ratio * (mid_cooldown - COOLDOWN_MIN_TAU2) as f64;
            scaled as u64
        } else {
            let excess = ratio - 1.0;
            let scaled = mid_cooldown as f64 + excess * (COOLDOWN_MAX_TAU2 - mid_cooldown) as f64;
            scaled.min(COOLDOWN_MAX_TAU2 as f64) as u64
        };

        let rate_limited = self.rate_limited_cooldown(raw_cooldown, tier_idx);
        rate_limited.clamp(COOLDOWN_MIN_TAU2, COOLDOWN_MAX_TAU2)
    }

    /// Update median snapshot for a tier
    ///
    /// Called at each τ₂ to maintain rolling median over τ₃ window.
    /// Also stores median history for 4 τ₃ smoothing and updates rate limit baseline.
    pub fn update_snapshot(&mut self, current_tau2: u64, node_type: NodeType) {
        let tier = node_type.tier_index();
        let tier_idx = tier as usize;
        let current_tau3 = current_tau2 / COOLDOWN_WINDOW_TAU2;

        let extended_window = COOLDOWN_WINDOW_TAU2 * COOLDOWN_SMOOTH_WINDOWS;
        let window_start = current_tau2.saturating_sub(extended_window);
        self.registrations.retain(|(tau2, t), _| {
            *t != tier || *tau2 >= window_start
        });

        let min_tau3 = current_tau3.saturating_sub(COOLDOWN_SMOOTH_WINDOWS);
        self.median_history.retain(|(tau3, t), _| {
            *t != tier || *tau3 >= min_tau3
        });

        let tau3_window_start = current_tau2.saturating_sub(COOLDOWN_WINDOW_TAU2);
        let mut counts: Vec<u64> = self
            .registrations
            .iter()
            .filter(|((tau2, t), _)| *t == tier && *tau2 >= tau3_window_start)
            .map(|(_, &count)| count)
            .collect();

        let snapshot = &mut self.snapshots[tier_idx];
        snapshot.counts_per_tau2 = self
            .registrations
            .iter()
            .filter(|((tau2, t), _)| *t == tier && *tau2 >= tau3_window_start)
            .map(|((tau2, _), &count)| (*tau2, count))
            .collect();
        snapshot.last_tau2 = current_tau2;

        if counts.is_empty() {
            snapshot.median = 0;
        } else {
            counts.sort();
            let mid = counts.len() / 2;
            snapshot.median = if counts.len() % 2 == 0 && mid > 0 {
                (counts[mid - 1] + counts[mid]) / 2
            } else {
                counts[mid]
            };
        }

        if snapshot.median > 0 {
            self.median_history.insert((current_tau3, tier), snapshot.median);
        }

        if current_tau2 % COOLDOWN_WINDOW_TAU2 == 0 {
            let current_cooldown = self.calculate_cooldown(current_tau2, node_type);
            self.previous_cooldown[tier_idx] = current_cooldown;
        }
    }

    /// Finalize τ₃ period: store median in history and update rate limit baseline
    ///
    /// Should be called at end of each τ₃ to commit the current median
    pub fn finalize_tau3(&mut self, tau3_index: u64, node_type: NodeType) {
        let tier = node_type.tier_index();
        let tier_idx = tier as usize;
        let median = self.snapshots[tier_idx].median;

        if median > 0 {
            self.median_history.insert((tau3_index, tier), median);
        }

        let tau2_at_tau3 = tau3_index * COOLDOWN_WINDOW_TAU2;
        self.previous_cooldown[tier_idx] = self.calculate_cooldown(tau2_at_tau3, node_type);
    }

    /// Get current median for a tier
    pub fn get_median(&self, node_type: NodeType) -> u64 {
        self.snapshots[node_type.tier_index() as usize].median
    }

    /// Get snapshot for a tier (for publishing in slice)
    pub fn get_snapshot(&self, node_type: NodeType) -> &MedianSnapshot {
        &self.snapshots[node_type.tier_index() as usize]
    }

    /// Verify that a claimed cooldown matches expected value
    ///
    /// Used by other nodes to verify registration cooldown
    pub fn verify_cooldown(
        &self,
        registration_tau2: u64,
        node_type: NodeType,
        claimed_cooldown: u64,
    ) -> bool {
        let tier = node_type.tier_index() as usize;
        let snapshot = &self.snapshots[tier];

        if snapshot.counts_per_tau2.is_empty() {
            return claimed_cooldown == COOLDOWN_DEFAULT_TAU2;
        }

        let expected = self.calculate_cooldown(registration_tau2, node_type);
        let tolerance = expected / 10 + 1;
        claimed_cooldown >= expected.saturating_sub(tolerance)
            && claimed_cooldown <= expected.saturating_add(tolerance)
    }
}

/// Extended PresenceProof with cooldown info
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CooldownPresenceInfo {
    /// Node is in cooldown
    pub in_cooldown: bool,
    /// Cooldown ends at this τ₂ (0 for active nodes)
    pub cooldown_until: u64,
}

/// Slice extension for cooldown verification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SliceCooldownData {
    /// Median snapshots at this slice (for independent verification)
    pub medians: [u64; 3],  // Full, Light, Client
    /// New registrations in this τ₂ per tier
    pub registrations: [u64; 3],
}
