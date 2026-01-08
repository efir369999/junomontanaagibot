//! Unit tests for consensus module
//!
//! NOTE: Lottery implementation was removed (grinding vulnerability).
//! These tests verify only the constants until lottery is reimplemented
//! with correct seed = SHA3(prev_slice_hash ‖ τ₂_index) formula.

use montana::{
    GRACE_PERIOD_SECS, SLOTS_PER_TAU2, SLOT_DURATION_SECS,
    FULL_NODE_CAP_PERCENT, LIGHT_NODE_CAP_PERCENT, LIGHT_CLIENT_CAP_PERCENT,
    LOTTERY_PRECISION,
};

#[test]
fn test_consensus_constants() {
    // Grace period: last 30 seconds of τ₂, no new presence submissions
    assert_eq!(GRACE_PERIOD_SECS, 30);

    // 10 slots per τ₂ (10 minutes), 1 minute each
    assert_eq!(SLOTS_PER_TAU2, 10);
    assert_eq!(SLOT_DURATION_SECS, 60);

    // Tier caps must sum to 100%
    assert_eq!(
        FULL_NODE_CAP_PERCENT + LIGHT_NODE_CAP_PERCENT + LIGHT_CLIENT_CAP_PERCENT,
        100
    );

    // Full nodes get majority but not all
    assert_eq!(FULL_NODE_CAP_PERCENT, 70);
    assert_eq!(LIGHT_NODE_CAP_PERCENT, 20);
    assert_eq!(LIGHT_CLIENT_CAP_PERCENT, 10);

    // Precision for weight calculations
    assert_eq!(LOTTERY_PRECISION, 1_000_000);
}

#[test]
fn test_tier_caps_prevent_centralization() {
    // Even if Full Nodes have 95% of raw weight, they can only win 70% of lotteries
    // This test documents the design intent

    let full_raw_weight: u64 = 95_000_000;
    let light_raw_weight: u64 = 4_000_000;
    let client_raw_weight: u64 = 1_000_000;
    let _total_raw = full_raw_weight + light_raw_weight + client_raw_weight;

    // Full nodes: 95% raw → 70% effective (capped)
    // Light nodes: 4% raw → 20% effective (boosted)
    // Clients: 1% raw → 10% effective (boosted)

    // Total effective must equal 100%
    assert_eq!(
        FULL_NODE_CAP_PERCENT + LIGHT_NODE_CAP_PERCENT + LIGHT_CLIENT_CAP_PERCENT,
        100
    );
}
