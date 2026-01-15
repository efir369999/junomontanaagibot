//! Unit tests for cooldown module

use montana::{
    AdaptiveCooldown, NodeType,
    COOLDOWN_DEFAULT_TAU2, COOLDOWN_MAX_TAU2, COOLDOWN_MIN_TAU2,
};

#[test]
fn test_genesis_cooldown() {
    let cooldown = AdaptiveCooldown::new();
    // Genesis: no history, should return default (1 τ₂)
    assert_eq!(cooldown.calculate_cooldown(0, NodeType::Full), COOLDOWN_DEFAULT_TAU2);
}

#[test]
fn test_median_calculation() {
    let mut cooldown = AdaptiveCooldown::new();

    // Simulate registrations over multiple τ₂
    for tau2 in 0..100 {
        for _ in 0..5 {
            cooldown.record_registration(tau2, NodeType::Full);
        }
        cooldown.update_snapshot(tau2, NodeType::Full);
    }

    // Median should be 5
    assert_eq!(cooldown.get_median(NodeType::Full), 5);
}

#[test]
fn test_cooldown_bounds() {
    let mut cooldown = AdaptiveCooldown::new();

    // Record very high registration count
    for _ in 0..1000 {
        cooldown.record_registration(100, NodeType::Full);
    }
    cooldown.update_snapshot(100, NodeType::Full);

    let calc = cooldown.calculate_cooldown(100, NodeType::Full);
    assert!(calc <= COOLDOWN_MAX_TAU2);
    assert!(calc >= COOLDOWN_MIN_TAU2);
}
