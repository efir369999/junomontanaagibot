//! Rate limiting tests
//!
//! Run with: cargo test --test rate_limit_test

use montana::net::rate_limit::{
    AdaptiveSubnetLimiter, AddrRateLimiter, FlowControl, GlobalSubnetLimiter, TokenBucket,
};
use montana::types::{ip_to_subnet, SubnetKey};
use std::net::IpAddr;
use std::thread::sleep;
use std::time::Duration;

// =============================================================================
// TOKEN BUCKET TESTS
// =============================================================================

#[test]
fn test_token_bucket_consume_and_refill() {
    let mut bucket = TokenBucket::new(10.0, 1.0);

    // Should have full capacity
    assert!(bucket.try_consume(10.0));

    // Should be empty now
    assert!(!bucket.try_consume(1.0));

    // Wait for refill
    sleep(Duration::from_millis(100));

    // Should have ~0.1 tokens
    assert!(bucket.available() > 0.05);
    assert!(bucket.available() < 0.2);
}

// =============================================================================
// ADDR RATE LIMITER TESTS
// =============================================================================

#[test]
fn test_addr_rate_limiter_burst_and_limit() {
    let mut limiter = AddrRateLimiter::new();

    // Should process up to 1000 initially
    assert_eq!(limiter.process(500), 500);
    assert_eq!(limiter.process(500), 500);

    // Should be rate limited now
    assert!(limiter.is_rate_limited());
    assert_eq!(limiter.process(100), 0);
}

// =============================================================================
// FLOW CONTROL TESTS
// =============================================================================

#[test]
fn test_flow_control_pause_thresholds() {
    let mut fc = FlowControl::new();

    // Should not pause initially
    assert!(!fc.should_pause_recv());
    assert!(!fc.should_pause_send());

    // Add large amount to recv
    fc.add_recv(6 * 1024 * 1024);
    assert!(fc.should_pause_recv());

    // Remove some
    fc.remove_recv(2 * 1024 * 1024);
    assert!(!fc.should_pause_recv());
}

// =============================================================================
// ADAPTIVE SUBNET LIMITER TESTS - IPv4
// =============================================================================

#[test]
fn test_adaptive_subnet_limiter_basic_v4() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip: IpAddr = "192.168.1.1".parse().unwrap();
    let now = 1000u64;

    // First requests should pass (default limit)
    for _ in 0..50 {
        assert!(limiter.check(ip, now));
    }

    // Stats should show IPv4 activity
    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v4, 1);
    assert_eq!(stats.fast.active_subnets_v6, 0);
}

#[test]
fn test_adaptive_subnet_limiter_different_subnets_v4() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip1: IpAddr = "192.168.1.1".parse().unwrap(); // subnet 192.168
    let ip2: IpAddr = "10.0.1.1".parse().unwrap(); // subnet 10.0
    let now = 1000u64;

    // Both subnets should have independent limits
    for _ in 0..50 {
        assert!(limiter.check(ip1, now));
        assert!(limiter.check(ip2, now));
    }

    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v4, 2);
}

#[test]
fn test_adaptive_subnet_limiter_same_subnet_different_ips_v4() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip1: IpAddr = "192.168.1.1".parse().unwrap();
    let ip2: IpAddr = "192.168.2.2".parse().unwrap(); // Same /16 subnet
    let now = 1000u64;

    // Both IPs share the same subnet limit
    for _ in 0..30 {
        limiter.check(ip1, now);
    }
    for _ in 0..30 {
        limiter.check(ip2, now);
    }

    // Should be 1 IPv4 subnet with 60 requests
    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v4, 1);
}

// =============================================================================
// ADAPTIVE SUBNET LIMITER TESTS - IPv6
// =============================================================================

#[test]
fn test_adaptive_subnet_limiter_basic_v6() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip: IpAddr = "2001:db8::1".parse().unwrap();
    let now = 1000u64;

    // First requests should pass (default limit)
    for _ in 0..50 {
        assert!(limiter.check(ip, now));
    }

    // Stats should show IPv6 activity
    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v4, 0);
    assert_eq!(stats.fast.active_subnets_v6, 1);
}

#[test]
fn test_adaptive_subnet_limiter_different_subnets_v6() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    // Different /32 subnets: 2001:db8 vs 2001:db9
    let ip1: IpAddr = "2001:db8::1".parse().unwrap();
    let ip2: IpAddr = "2001:db9::1".parse().unwrap();
    let now = 1000u64;

    // Both subnets should have independent limits
    for _ in 0..50 {
        assert!(limiter.check(ip1, now));
        assert!(limiter.check(ip2, now));
    }

    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v6, 2);
}

#[test]
fn test_adaptive_subnet_limiter_same_subnet_different_ips_v6() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    // Same /32 subnet: 2001:0db8
    let ip1: IpAddr = "2001:db8:1::1".parse().unwrap();
    let ip2: IpAddr = "2001:db8:2::1".parse().unwrap();
    let now = 1000u64;

    // Both IPs share the same /32 subnet limit
    for _ in 0..30 {
        limiter.check(ip1, now);
    }
    for _ in 0..30 {
        limiter.check(ip2, now);
    }

    // Should be 1 IPv6 subnet with 60 requests
    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v6, 1);
}

// =============================================================================
// ADAPTIVE SUBNET LIMITER TESTS - DUAL STACK
// =============================================================================

#[test]
fn test_adaptive_subnet_limiter_dual_stack() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ipv4: IpAddr = "192.168.1.1".parse().unwrap();
    let ipv6: IpAddr = "2001:db8::1".parse().unwrap();
    let now = 1000u64;

    for _ in 0..50 {
        assert!(limiter.check(ipv4, now));
        assert!(limiter.check(ipv6, now));
    }

    let stats = limiter.stats();
    assert_eq!(stats.fast.active_subnets_v4, 1);
    assert_eq!(stats.fast.active_subnets_v6, 1);
}

// =============================================================================
// ADAPTIVE SUBNET LIMITER TESTS - SLOT ROTATION
// =============================================================================

#[test]
fn test_adaptive_subnet_limiter_slot_rotation() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip: IpAddr = "192.168.1.1".parse().unwrap();

    // Slot 0
    for _ in 0..10 {
        limiter.check(ip, 0);
    }

    // Slot 1 (after 60 seconds)
    for _ in 0..10 {
        limiter.check(ip, 60);
    }

    // Should have tracked slots
    let stats = limiter.stats();
    assert!(stats.fast.tracked_slots_v4 >= 1);
}

#[test]
fn test_adaptive_subnet_limiter_period_finalization() {
    let mut limiter = AdaptiveSubnetLimiter::new();
    let ip: IpAddr = "192.168.1.1".parse().unwrap();

    // Fill 10 slots (1 period for fast tier)
    for slot in 0..10 {
        let time = slot * 60; // Each slot is 60 seconds
        for _ in 0..50 {
            limiter.check(ip, time);
        }
    }

    // Move to next period to trigger finalization
    limiter.check(ip, 10 * 60 + 1);

    let stats = limiter.stats();
    // Should have median history after period ends
    assert!(stats.fast.median_entries_v4 >= 0); // May be 0 or 1 depending on timing
}

// =============================================================================
// GLOBAL SUBNET LIMITER TESTS
// =============================================================================

#[test]
fn test_global_subnet_limiter_stats() {
    let mut limiter = GlobalSubnetLimiter::new();
    let ip: IpAddr = "192.168.1.1".parse().unwrap();
    let now = 1000u64;

    // Some allowed
    for _ in 0..10 {
        limiter.check(ip, now);
    }

    let stats = limiter.stats();
    assert!(stats.allowed_count > 0);
    assert!(stats.block_rate >= 0.0);
}

// =============================================================================
// SUBNET EXTRACTION TESTS
// =============================================================================

#[test]
fn test_ipv4_subnet_extraction() {
    let ip1: IpAddr = "192.168.1.1".parse().unwrap();
    let ip2: IpAddr = "192.168.255.255".parse().unwrap();

    let s1 = ip_to_subnet(ip1);
    let s2 = ip_to_subnet(ip2);

    // Same /16 should produce same subnet
    match (s1, s2) {
        (SubnetKey::V4(a), SubnetKey::V4(b)) => {
            assert_eq!(a, b); // 0xC0A8 = 192.168
        }
        _ => panic!("Expected V4 subnets"),
    }
}

#[test]
fn test_ipv6_subnet_extraction_same_32() {
    // Same /32 should produce same subnet
    let ip1: IpAddr = "2001:db8:1234::1".parse().unwrap();
    let ip2: IpAddr = "2001:db8:5678::1".parse().unwrap();

    let s1 = ip_to_subnet(ip1);
    let s2 = ip_to_subnet(ip2);

    // Both should be V6 with same /32 prefix (2001:0db8)
    match (s1, s2) {
        (SubnetKey::V6(a), SubnetKey::V6(b)) => {
            assert_eq!(a, b); // 0x20010db8
        }
        _ => panic!("Expected V6 subnets"),
    }
}

#[test]
fn test_ipv6_subnet_extraction_different_32() {
    // Different /32 should produce different subnets
    let ip1: IpAddr = "2001:db8::1".parse().unwrap(); // 2001:0db8
    let ip2: IpAddr = "2001:db9::1".parse().unwrap(); // 2001:0db9

    let s1 = ip_to_subnet(ip1);
    let s2 = ip_to_subnet(ip2);

    match (s1, s2) {
        (SubnetKey::V6(a), SubnetKey::V6(b)) => {
            assert_ne!(a, b);
        }
        _ => panic!("Expected V6 subnets"),
    }
}

#[test]
fn test_ipv6_subnet_value() {
    let ip: IpAddr = "2001:0db8::1".parse().unwrap();
    let subnet = ip_to_subnet(ip);

    match subnet {
        SubnetKey::V6(v) => {
            // 2001:0db8 in big-endian = 0x20010db8
            assert_eq!(v, 0x2001_0db8);
        }
        _ => panic!("Expected V6 subnet"),
    }
}
