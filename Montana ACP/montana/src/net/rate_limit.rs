//! Token bucket rate limiting for DoS protection

use std::time::Instant;

#[derive(Debug, Clone)]
pub struct TokenBucket {
    tokens: f64,
    capacity: f64,
    rate_per_sec: f64,
    last_update: Instant,
}

impl TokenBucket {
    pub fn new(capacity: f64, rate_per_sec: f64) -> Self {
        Self {
            tokens: capacity,
            capacity,
            rate_per_sec,
            last_update: Instant::now(),
        }
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_update).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.rate_per_sec).min(self.capacity);
        self.last_update = now;
    }

    pub fn try_consume(&mut self, tokens: f64) -> bool {
        self.refill();
        if self.tokens >= tokens {
            self.tokens -= tokens;
            true
        } else {
            false
        }
    }

    pub fn available(&mut self) -> f64 {
        self.refill();
        self.tokens
    }

    pub fn consume(&mut self, tokens: f64) {
        self.refill();
        self.tokens -= tokens;
    }

    pub fn tokens(&self) -> f64 {
        self.tokens
    }
}

/// Bitcoin Core: 0.1 addr/sec, 1000 burst
#[derive(Debug, Clone)]
pub struct AddrRateLimiter {
    bucket: TokenBucket,
}

impl AddrRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(1000.0, 0.1) }
    }

    pub fn with_limits(capacity: f64, rate_per_sec: f64) -> Self {
        Self { bucket: TokenBucket::new(capacity, rate_per_sec) }
    }

    pub fn process(&mut self, count: usize) -> usize {
        let available = self.bucket.available() as usize;
        let to_process = count.min(available);
        if to_process > 0 {
            self.bucket.consume(to_process as f64);
        }
        to_process
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }
}

impl Default for AddrRateLimiter {
    fn default() -> Self { Self::new() }
}

#[derive(Debug, Clone)]
pub struct InvRateLimiter {
    bucket: TokenBucket,
}

impl InvRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(5000.0, 10.0) }
    }

    pub fn try_consume(&mut self, count: usize) -> bool {
        self.bucket.try_consume(count as f64)
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }
}

impl Default for InvRateLimiter {
    fn default() -> Self { Self::new() }
}

#[derive(Debug, Clone)]
pub struct GetDataRateLimiter {
    bucket: TokenBucket,
}

impl GetDataRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(1000.0, 5.0) }
    }

    pub fn try_consume(&mut self, count: usize) -> bool {
        self.bucket.try_consume(count as f64)
    }
}

impl Default for GetDataRateLimiter {
    fn default() -> Self { Self::new() }
}

/// Headers validation is CPU-intensive
#[derive(Debug, Clone)]
pub struct HeadersRateLimiter {
    bucket: TokenBucket,
}

impl HeadersRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(5000.0, 10.0) }
    }

    pub fn try_consume(&mut self, count: usize) -> bool {
        self.bucket.try_consume(count as f64)
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }

    pub fn available(&mut self) -> usize {
        self.bucket.available() as usize
    }
}

impl Default for HeadersRateLimiter {
    fn default() -> Self { Self::new() }
}

/// Each request can trigger 2GB response
#[derive(Debug, Clone)]
pub struct GetSlicesRateLimiter {
    bucket: TokenBucket,
}

impl GetSlicesRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(5.0, 1.0) }
    }

    pub fn try_consume(&mut self) -> bool {
        self.bucket.try_consume(1.0)
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }
}

impl Default for GetSlicesRateLimiter {
    fn default() -> Self { Self::new() }
}

#[derive(Debug, Clone)]
pub struct SliceRateLimiter {
    bucket: TokenBucket,
}

impl SliceRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(50.0, 0.1) }
    }

    pub fn try_consume(&mut self) -> bool {
        self.bucket.try_consume(1.0)
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }
}

impl Default for SliceRateLimiter {
    fn default() -> Self { Self::new() }
}

/// Rate limiter for AuthChallenge messages.
///
/// AuthChallenge triggers ML-DSA-65 signing (~1-5ms CPU).
/// Strict limits prevent CPU exhaustion attacks on hardcoded nodes.
///
/// Limits: 3 burst, 0.05/sec recovery (1 per 20 seconds).
/// This allows legitimate bootstrap queries while blocking flood attacks.
#[derive(Debug, Clone)]
pub struct AuthChallengeRateLimiter {
    bucket: TokenBucket,
}

impl AuthChallengeRateLimiter {
    pub fn new() -> Self {
        Self { bucket: TokenBucket::new(3.0, 0.05) }
    }

    pub fn try_consume(&mut self) -> bool {
        self.bucket.try_consume(1.0)
    }

    pub fn is_rate_limited(&mut self) -> bool {
        self.bucket.available() < 1.0
    }
}

impl Default for AuthChallengeRateLimiter {
    fn default() -> Self { Self::new() }
}

#[derive(Debug, Clone)]
pub struct PeerRateLimits {
    pub addr: AddrRateLimiter,
    pub inv: InvRateLimiter,
    pub getdata: GetDataRateLimiter,
    pub headers: HeadersRateLimiter,
    pub getslices: GetSlicesRateLimiter,
    pub slice: SliceRateLimiter,
    pub auth_challenge: AuthChallengeRateLimiter,
}

impl PeerRateLimits {
    pub fn new() -> Self {
        Self {
            addr: AddrRateLimiter::new(),
            inv: InvRateLimiter::new(),
            getdata: GetDataRateLimiter::new(),
            headers: HeadersRateLimiter::new(),
            getslices: GetSlicesRateLimiter::new(),
            slice: SliceRateLimiter::new(),
            auth_challenge: AuthChallengeRateLimiter::new(),
        }
    }
}

impl Default for PeerRateLimits {
    fn default() -> Self { Self::new() }
}

#[derive(Debug, Clone)]
pub struct FlowControl {
    pub recv_queue_size: usize,
    pub send_queue_size: usize,
    pub max_recv_queue: usize,
    pub max_send_queue: usize,
    pub pause_recv: bool,
    pub pause_send: bool,
}

impl FlowControl {
    pub fn new() -> Self {
        Self {
            recv_queue_size: 0,
            send_queue_size: 0,
            max_recv_queue: 5 * 1024 * 1024,
            max_send_queue: 1024 * 1024,
            pause_recv: false,
            pause_send: false,
        }
    }

    pub fn update_recv(&mut self, size: usize) {
        self.recv_queue_size = size;
        self.pause_recv = self.recv_queue_size > self.max_recv_queue;
    }

    pub fn update_send(&mut self, size: usize) {
        self.send_queue_size = size;
        self.pause_send = self.send_queue_size > self.max_send_queue;
    }

    pub fn add_recv(&mut self, bytes: usize) {
        self.recv_queue_size = self.recv_queue_size.saturating_add(bytes);
        self.pause_recv = self.recv_queue_size > self.max_recv_queue;
    }

    pub fn remove_recv(&mut self, bytes: usize) {
        self.recv_queue_size = self.recv_queue_size.saturating_sub(bytes);
        self.pause_recv = self.recv_queue_size > self.max_recv_queue;
    }

    pub fn add_send(&mut self, bytes: usize) {
        self.send_queue_size = self.send_queue_size.saturating_add(bytes);
        self.pause_send = self.send_queue_size > self.max_send_queue;
    }

    pub fn remove_send(&mut self, bytes: usize) {
        self.send_queue_size = self.send_queue_size.saturating_sub(bytes);
        self.pause_send = self.send_queue_size > self.max_send_queue;
    }

    pub fn should_pause_recv(&self) -> bool {
        self.pause_recv
    }

    pub fn should_pause_send(&self) -> bool {
        self.pause_send
    }
}

impl Default for FlowControl {
    fn default() -> Self { Self::new() }
}

use crate::types::{ip_to_subnet, Subnet16, Subnet32, SubnetKey};
use std::collections::{HashMap, VecDeque};
use std::net::IpAddr;

const FAST_SLOT_SECS: u64 = 60;
const FAST_PERIOD_SLOTS: u64 = 10;
const FAST_SMOOTH_PERIODS: u64 = 4;
const FAST_MAX_CHANGE_PERCENT: u64 = 20;
const FAST_MIN_REQUESTS: u64 = 10;
const FAST_MAX_REQUESTS: u64 = 500;
const FAST_DEFAULT_REQUESTS: u64 = 100;

const SLOW_SLOT_SECS: u64 = 600;
const SLOW_PERIOD_SLOTS: u64 = 144;
const SLOW_SMOOTH_PERIODS: u64 = 4;
const SLOW_MAX_CHANGE_PERCENT: u64 = 20;
const SLOW_MIN_REQUESTS: u64 = 50;
const SLOW_MAX_REQUESTS: u64 = 2000;
const SLOW_DEFAULT_REQUESTS: u64 = 500;

/// 50k IPv6 /32 subnets ≈ 200 MB
const MAX_TRACKED_SUBNETS_V6: usize = 50_000;
const V6_EVICTION_BATCH: usize = 5_000;

#[derive(Debug, Clone)]
struct AdaptiveSubnetCore {
    slot_secs: u64,
    period_slots: u64,
    smooth_periods: u64,
    max_change_percent: u64,
    min_requests: u64,
    max_requests: u64,
    default_requests: u64,

    v4_requests: HashMap<(u64, Subnet16), u64>,
    v4_median_history: HashMap<(u64, Subnet16), u64>,
    v4_previous_limit: HashMap<Subnet16, u64>,
    v4_current_counts: HashMap<Subnet16, u64>,

    v6_requests: HashMap<(u64, Subnet32), u64>,
    v6_median_history: HashMap<(u64, Subnet32), u64>,
    v6_previous_limit: HashMap<Subnet32, u64>,
    v6_current_counts: HashMap<Subnet32, u64>,
    v6_access_order: VecDeque<Subnet32>,

    current_slot: u64,
}

impl AdaptiveSubnetCore {
    fn new(
        slot_secs: u64,
        period_slots: u64,
        smooth_periods: u64,
        max_change_percent: u64,
        min_requests: u64,
        max_requests: u64,
        default_requests: u64,
    ) -> Self {
        Self {
            slot_secs,
            period_slots,
            smooth_periods,
            max_change_percent,
            min_requests,
            max_requests,
            default_requests,
            // IPv4
            v4_requests: HashMap::new(),
            v4_median_history: HashMap::new(),
            v4_previous_limit: HashMap::new(),
            v4_current_counts: HashMap::new(),
            // IPv6
            v6_requests: HashMap::new(),
            v6_median_history: HashMap::new(),
            v6_previous_limit: HashMap::new(),
            v6_current_counts: HashMap::new(),
            v6_access_order: VecDeque::new(),
            current_slot: 0,
        }
    }

    /// Check and record request. Returns true if allowed.
    fn check(&mut self, subnet: SubnetKey, now_secs: u64) -> bool {
        self.maybe_rotate_slot(now_secs);

        match subnet {
            SubnetKey::V4(s) => self.check_v4(s),
            SubnetKey::V6(s) => self.check_v6(s),
        }
    }

    /// Check IPv4 subnet
    fn check_v4(&mut self, subnet: Subnet16) -> bool {
        let limit = self.calculate_limit_v4(subnet);
        let current = self.v4_current_counts.entry(subnet).or_insert(0);

        if *current >= limit {
            return false;
        }

        *current += 1;
        true
    }

    /// Check IPv6 subnet with LRU tracking
    fn check_v6(&mut self, subnet: Subnet32) -> bool {
        // LRU eviction before adding
        self.maybe_evict_v6();

        let limit = self.calculate_limit_v6(subnet);
        let current = self.v6_current_counts.entry(subnet).or_insert(0);

        if *current >= limit {
            return false;
        }

        *current += 1;

        // Update LRU order
        self.touch_v6(subnet);
        true
    }

    /// Record request without checking
    fn record(&mut self, subnet: SubnetKey, now_secs: u64) {
        self.maybe_rotate_slot(now_secs);

        match subnet {
            SubnetKey::V4(s) => {
                *self.v4_current_counts.entry(s).or_insert(0) += 1;
            }
            SubnetKey::V6(s) => {
                self.maybe_evict_v6();
                *self.v6_current_counts.entry(s).or_insert(0) += 1;
                self.touch_v6(s);
            }
        }
    }

    /// Get current limit for subnet
    fn get_limit(&self, subnet: SubnetKey) -> u64 {
        match subnet {
            SubnetKey::V4(s) => self.calculate_limit_v4(s),
            SubnetKey::V6(s) => self.calculate_limit_v6(s),
        }
    }

    fn smoothed_median_v4(&self, subnet: Subnet16) -> u64 {
        let current_period = self.current_slot / self.period_slots;

        let mut medians = Vec::new();
        for i in 0..self.smooth_periods {
            let period_idx = current_period.saturating_sub(i);
            if let Some(&median) = self.v4_median_history.get(&(period_idx, subnet)) {
                if median > 0 {
                    medians.push(median);
                }
            }
        }

        if medians.is_empty() {
            return 0;
        }

        let sum: u64 = medians.iter().sum();
        sum / medians.len() as u64
    }

    fn rate_limited_v4(&self, raw_limit: u64, subnet: Subnet16) -> u64 {
        let previous = self.v4_previous_limit.get(&subnet).copied().unwrap_or(0);

        if previous == 0 {
            return raw_limit;
        }

        let max_change = (previous * self.max_change_percent) / 100;
        let max_change = max_change.max(self.min_requests);

        if raw_limit > previous {
            raw_limit.min(previous.saturating_add(max_change))
        } else {
            raw_limit.max(previous.saturating_sub(max_change))
        }
    }

    fn calculate_limit_v4(&self, subnet: Subnet16) -> u64 {
        let median = self.smoothed_median_v4(subnet);

        if median == 0 {
            return self.default_requests;
        }

        let current = self.v4_current_counts.get(&subnet).copied().unwrap_or(0);
        let ratio = current as f64 / median as f64;
        let mid_limit = (self.min_requests + self.max_requests) / 2;

        let raw_limit = if ratio <= 1.0 {
            let scaled = self.max_requests as f64
                - ratio * (self.max_requests - mid_limit) as f64;
            scaled as u64
        } else {
            let excess = ratio - 1.0;
            let scaled = mid_limit as f64
                - excess * (mid_limit - self.min_requests) as f64;
            scaled.max(self.min_requests as f64) as u64
        };

        let limited = self.rate_limited_v4(raw_limit, subnet);
        limited.clamp(self.min_requests, self.max_requests)
    }

    fn smoothed_median_v6(&self, subnet: Subnet32) -> u64 {
        let current_period = self.current_slot / self.period_slots;

        let mut medians = Vec::new();
        for i in 0..self.smooth_periods {
            let period_idx = current_period.saturating_sub(i);
            if let Some(&median) = self.v6_median_history.get(&(period_idx, subnet)) {
                if median > 0 {
                    medians.push(median);
                }
            }
        }

        if medians.is_empty() {
            return 0;
        }

        let sum: u64 = medians.iter().sum();
        sum / medians.len() as u64
    }

    fn rate_limited_v6(&self, raw_limit: u64, subnet: Subnet32) -> u64 {
        let previous = self.v6_previous_limit.get(&subnet).copied().unwrap_or(0);

        if previous == 0 {
            return raw_limit;
        }

        let max_change = (previous * self.max_change_percent) / 100;
        let max_change = max_change.max(self.min_requests);

        if raw_limit > previous {
            raw_limit.min(previous.saturating_add(max_change))
        } else {
            raw_limit.max(previous.saturating_sub(max_change))
        }
    }

    fn calculate_limit_v6(&self, subnet: Subnet32) -> u64 {
        let median = self.smoothed_median_v6(subnet);

        if median == 0 {
            return self.default_requests;
        }

        let current = self.v6_current_counts.get(&subnet).copied().unwrap_or(0);
        let ratio = current as f64 / median as f64;
        let mid_limit = (self.min_requests + self.max_requests) / 2;

        let raw_limit = if ratio <= 1.0 {
            let scaled = self.max_requests as f64
                - ratio * (self.max_requests - mid_limit) as f64;
            scaled as u64
        } else {
            let excess = ratio - 1.0;
            let scaled = mid_limit as f64
                - excess * (mid_limit - self.min_requests) as f64;
            scaled.max(self.min_requests as f64) as u64
        };

        let limited = self.rate_limited_v6(raw_limit, subnet);
        limited.clamp(self.min_requests, self.max_requests)
    }

    fn touch_v6(&mut self, subnet: Subnet32) {
        self.v6_access_order.retain(|&s| s != subnet);
        self.v6_access_order.push_back(subnet);
    }

    fn maybe_evict_v6(&mut self) {
        let unique_subnets = self.v6_current_counts.len()
            + self.v6_previous_limit.len()
            + self.v6_median_history.values().count();

        if unique_subnets < MAX_TRACKED_SUBNETS_V6 {
            return;
        }

        let to_evict: Vec<Subnet32> = self
            .v6_access_order
            .drain(..V6_EVICTION_BATCH.min(self.v6_access_order.len()))
            .collect();

        for subnet in to_evict {
            self.v6_current_counts.remove(&subnet);
            self.v6_previous_limit.remove(&subnet);
            self.v6_median_history.retain(|(_, s), _| *s != subnet);
            self.v6_requests.retain(|(_, s), _| *s != subnet);
        }
    }

    fn maybe_rotate_slot(&mut self, now_secs: u64) {
        let new_slot = now_secs / self.slot_secs;

        if new_slot <= self.current_slot {
            return;
        }

        for (subnet, count) in self.v4_current_counts.drain() {
            self.v4_requests.insert((self.current_slot, subnet), count);
        }

        for (subnet, count) in self.v6_current_counts.drain() {
            self.v6_requests.insert((self.current_slot, subnet), count);
        }

        let old_period = self.current_slot / self.period_slots;
        let new_period = new_slot / self.period_slots;

        if new_period > old_period {
            self.finalize_period(old_period);
            self.cleanup_old_data(new_period);
        }

        self.current_slot = new_slot;
    }

    fn finalize_period(&mut self, period_idx: u64) {
        let period_start = period_idx * self.period_slots;
        let period_end = period_start + self.period_slots;

        let mut v4_counts: HashMap<Subnet16, Vec<u64>> = HashMap::new();
        for ((slot, subnet), count) in &self.v4_requests {
            if *slot >= period_start && *slot < period_end {
                v4_counts.entry(*subnet).or_default().push(*count);
            }
        }
        for (subnet, mut counts) in v4_counts {
            if counts.is_empty() {
                continue;
            }
            counts.sort_unstable();
            let mid = counts.len() / 2;
            let median = if counts.len() % 2 == 0 && mid > 0 {
                (counts[mid - 1] + counts[mid]) / 2
            } else {
                counts[mid]
            };
            self.v4_median_history.insert((period_idx, subnet), median);
            self.v4_previous_limit.insert(subnet, self.calculate_limit_v4(subnet));
        }

        let mut v6_counts: HashMap<Subnet32, Vec<u64>> = HashMap::new();
        for ((slot, subnet), count) in &self.v6_requests {
            if *slot >= period_start && *slot < period_end {
                v6_counts.entry(*subnet).or_default().push(*count);
            }
        }
        for (subnet, mut counts) in v6_counts {
            if counts.is_empty() {
                continue;
            }
            counts.sort_unstable();
            let mid = counts.len() / 2;
            let median = if counts.len() % 2 == 0 && mid > 0 {
                (counts[mid - 1] + counts[mid]) / 2
            } else {
                counts[mid]
            };
            self.v6_median_history.insert((period_idx, subnet), median);
            self.v6_previous_limit.insert(subnet, self.calculate_limit_v6(subnet));
        }
    }

    fn cleanup_old_data(&mut self, current_period: u64) {
        let min_period = current_period.saturating_sub(self.smooth_periods);
        let min_slot = min_period * self.period_slots;

        self.v4_requests.retain(|(slot, _), _| *slot >= min_slot);
        self.v4_median_history.retain(|(period, _), _| *period >= min_period);
        let active_v4: std::collections::HashSet<_> = self
            .v4_median_history
            .keys()
            .map(|(_, subnet)| *subnet)
            .collect();
        self.v4_previous_limit.retain(|subnet, _| active_v4.contains(subnet));

        self.v6_requests.retain(|(slot, _), _| *slot >= min_slot);
        self.v6_median_history.retain(|(period, _), _| *period >= min_period);
        let active_v6: std::collections::HashSet<_> = self
            .v6_median_history
            .keys()
            .map(|(_, subnet)| *subnet)
            .collect();
        self.v6_previous_limit.retain(|subnet, _| active_v6.contains(subnet));
        self.v6_access_order.retain(|s| active_v6.contains(s));
    }

    fn stats(&self) -> AdaptiveTierStats {
        AdaptiveTierStats {
            current_slot: self.current_slot,
            active_subnets_v4: self.v4_current_counts.len(),
            active_subnets_v6: self.v6_current_counts.len(),
            tracked_slots_v4: self.v4_requests.len(),
            tracked_slots_v6: self.v6_requests.len(),
            median_entries_v4: self.v4_median_history.len(),
            median_entries_v6: self.v6_median_history.len(),
        }
    }
}

/// Statistics for a single tier (dual-stack)
#[derive(Debug, Clone)]
pub struct AdaptiveTierStats {
    pub current_slot: u64,
    /// Active IPv4 /16 subnets in current slot
    pub active_subnets_v4: usize,
    /// Active IPv6 /32 subnets in current slot
    pub active_subnets_v6: usize,
    /// Tracked IPv4 slot entries
    pub tracked_slots_v4: usize,
    /// Tracked IPv6 slot entries
    pub tracked_slots_v6: usize,
    /// IPv4 median history entries
    pub median_entries_v4: usize,
    /// IPv6 median history entries
    pub median_entries_v6: usize,
}

/// Fast tier: minutes scale, slow tier: days scale (Erebus resistance)
pub struct AdaptiveSubnetLimiter {
    fast: AdaptiveSubnetCore,
    slow: AdaptiveSubnetCore,
}

impl AdaptiveSubnetLimiter {
    pub fn new() -> Self {
        Self {
            fast: AdaptiveSubnetCore::new(
                FAST_SLOT_SECS,
                FAST_PERIOD_SLOTS,
                FAST_SMOOTH_PERIODS,
                FAST_MAX_CHANGE_PERCENT,
                FAST_MIN_REQUESTS,
                FAST_MAX_REQUESTS,
                FAST_DEFAULT_REQUESTS,
            ),
            slow: AdaptiveSubnetCore::new(
                SLOW_SLOT_SECS,
                SLOW_PERIOD_SLOTS,
                SLOW_SMOOTH_PERIODS,
                SLOW_MAX_CHANGE_PERCENT,
                SLOW_MIN_REQUESTS,
                SLOW_MAX_REQUESTS,
                SLOW_DEFAULT_REQUESTS,
            ),
        }
    }

    pub fn check(&mut self, ip: IpAddr, now_secs: u64) -> bool {
        let subnet = ip_to_subnet(ip);
        let fast_ok = self.fast.check(subnet, now_secs);
        let slow_ok = self.slow.check(subnet, now_secs);
        fast_ok && slow_ok
    }

    pub fn record(&mut self, ip: IpAddr, now_secs: u64) {
        let subnet = ip_to_subnet(ip);
        self.fast.record(subnet, now_secs);
        self.slow.record(subnet, now_secs);
    }

    pub fn get_limits(&self, ip: IpAddr) -> (u64, u64) {
        let subnet = ip_to_subnet(ip);
        (self.fast.get_limit(subnet), self.slow.get_limit(subnet))
    }

    pub fn check_fast(&mut self, ip: IpAddr, now_secs: u64) -> bool {
        let subnet = ip_to_subnet(ip);
        self.fast.check(subnet, now_secs)
    }

    pub fn check_slow(&mut self, ip: IpAddr, now_secs: u64) -> bool {
        let subnet = ip_to_subnet(ip);
        self.slow.check(subnet, now_secs)
    }

    pub fn stats(&self) -> AdaptiveSubnetStats {
        AdaptiveSubnetStats {
            fast: self.fast.stats(),
            slow: self.slow.stats(),
        }
    }
}

impl Default for AdaptiveSubnetLimiter {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone)]
pub struct AdaptiveSubnetStats {
    pub fast: AdaptiveTierStats,
    pub slow: AdaptiveTierStats,
}

pub struct GlobalSubnetLimiter {
    limiter: AdaptiveSubnetLimiter,
    blocked_count: u64,
    allowed_count: u64,
}

impl GlobalSubnetLimiter {
    pub fn new() -> Self {
        Self {
            limiter: AdaptiveSubnetLimiter::new(),
            blocked_count: 0,
            allowed_count: 0,
        }
    }

    pub fn check(&mut self, ip: IpAddr, now_secs: u64) -> bool {
        if self.limiter.check(ip, now_secs) {
            self.allowed_count += 1;
            true
        } else {
            self.blocked_count += 1;
            false
        }
    }

    pub fn check_fast(&mut self, ip: IpAddr, now_secs: u64) -> bool {
        if self.limiter.check_fast(ip, now_secs) {
            self.allowed_count += 1;
            true
        } else {
            self.blocked_count += 1;
            false
        }
    }

    pub fn record(&mut self, ip: IpAddr, now_secs: u64) {
        self.limiter.record(ip, now_secs);
    }

    pub fn get_limits(&self, ip: IpAddr) -> (u64, u64) {
        self.limiter.get_limits(ip)
    }

    pub fn stats(&self) -> GlobalSubnetStats {
        GlobalSubnetStats {
            tiers: self.limiter.stats(),
            allowed_count: self.allowed_count,
            blocked_count: self.blocked_count,
            block_rate: if self.allowed_count + self.blocked_count > 0 {
                self.blocked_count as f64 / (self.allowed_count + self.blocked_count) as f64
            } else {
                0.0
            },
        }
    }

    pub fn reset_counters(&mut self) {
        self.allowed_count = 0;
        self.blocked_count = 0;
    }
}

impl Default for GlobalSubnetLimiter {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone)]
pub struct GlobalSubnetStats {
    pub tiers: AdaptiveSubnetStats,
    pub allowed_count: u64,
    pub blocked_count: u64,
    pub block_rate: f64,
}
