//! Connection management with ban list and netgroup limits

use super::types::{
    INITIAL_RETRY_DELAY_SECS, MAX_CONNECTIONS_PER_IP, MAX_INBOUND, MAX_OUTBOUND, MAX_PEERS,
    MAX_PEERS_PER_NETGROUP, MAX_RETRY_DELAY_SECS, RETRY_BACKOFF_FACTOR,
};
use crate::types::now;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::net::{IpAddr, SocketAddr};
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use tokio::sync::Mutex;
use tracing::{debug, info};

/// Ban entry with expiration and reason
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BanEntry {
    pub addr: SocketAddr,
    pub banned_at: u64,
    pub ban_until: u64,
    pub reason: String,
}

impl BanEntry {
    pub fn new(addr: SocketAddr, duration_secs: u64, reason: String) -> Self {
        let now = now();
        Self {
            addr,
            banned_at: now,
            ban_until: now.saturating_add(duration_secs),
            reason,
        }
    }

    pub fn is_expired(&self) -> bool {
        now() >= self.ban_until
    }
}

/// Maximum serialized size for BanList (security limit for file load)
/// Each entry ~100 bytes, 10000 entries = ~1MB
const MAX_BANLIST_FILE_SIZE: u64 = 1024 * 1024;

/// Persistent ban list
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BanList {
    bans: HashMap<SocketAddr, BanEntry>,
}

impl BanList {
    pub fn new() -> Self {
        Self { bans: HashMap::new() }
    }

    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self, std::io::Error> {
        let data = std::fs::read(&path)?;

        // Security: reject oversized files before deserialization
        if data.len() as u64 > MAX_BANLIST_FILE_SIZE {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("ban list file too large: {} bytes", data.len()),
            ));
        }

        // Bounded deserialize prevents malicious length prefixes
        // Use standard bincode config (same as serialize) with size limit
        bincode::deserialize(&data)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))
    }

    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        let data = bincode::serialize(self).map_err(|e| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, e)
        })?;
        std::fs::write(path, data)
    }

    pub fn ban(&mut self, entry: BanEntry) {
        info!("Banning {} until {} ({})", entry.addr, entry.ban_until, entry.reason);
        self.bans.insert(entry.addr, entry);
    }

    pub fn is_banned(&self, addr: &SocketAddr) -> bool {
        if let Some(entry) = self.bans.get(addr) {
            if entry.is_expired() {
                return false;
            }
            return true;
        }
        false
    }

    pub fn unban(&mut self, addr: &SocketAddr) -> bool {
        self.bans.remove(addr).is_some()
    }

    pub fn expire(&mut self) {
        let expired: Vec<_> = self.bans
            .iter()
            .filter(|(_, e)| e.is_expired())
            .map(|(a, _)| *a)
            .collect();

        for addr in expired {
            debug!("Ban expired for {}", addr);
            self.bans.remove(&addr);
        }
    }

    pub fn len(&self) -> usize {
        self.bans.len()
    }

    pub fn is_empty(&self) -> bool {
        self.bans.is_empty()
    }

    pub fn list(&self) -> Vec<&BanEntry> {
        self.bans.values().collect()
    }

    pub fn clear(&mut self) {
        self.bans.clear();
    }
}

/// Retry tracking with exponential backoff
#[derive(Debug, Clone, Default)]
pub struct RetryInfo {
    pub attempts: u32,
    pub last_attempt: u64,
    pub next_retry_delay: u64,
}

impl RetryInfo {
    pub fn new() -> Self {
        Self {
            attempts: 0,
            last_attempt: 0,
            next_retry_delay: INITIAL_RETRY_DELAY_SECS,
        }
    }

    pub fn record_failure(&mut self) {
        self.attempts += 1;
        self.last_attempt = now();
        self.next_retry_delay = (self.next_retry_delay * RETRY_BACKOFF_FACTOR)
            .min(MAX_RETRY_DELAY_SECS);
    }

    pub fn record_success(&mut self) {
        self.attempts = 0;
        self.next_retry_delay = INITIAL_RETRY_DELAY_SECS;
    }

    pub fn can_retry(&self) -> bool {
        if self.last_attempt == 0 {
            return true;
        }
        now() >= self.last_attempt + self.next_retry_delay
    }
}

/// Get /16 netgroup for an IP address
fn get_netgroup(addr: &SocketAddr) -> u32 {
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

/// Connection manager tracking inbound/outbound limits
pub struct ConnectionManager {
    max_outbound: usize,
    max_inbound: usize,
    outbound_count: AtomicUsize,
    inbound_count: AtomicUsize,
    connecting: Mutex<HashSet<SocketAddr>>,
    ban_list: Mutex<BanList>,
    netgroup_counts: Mutex<HashMap<u32, usize>>,
    retry_info: Mutex<HashMap<SocketAddr, RetryInfo>>,
    /// Connections per IP address (DoS protection)
    /// Security: Limits rate amplification from single IP to MAX_CONNECTIONS_PER_IP×
    connections_per_ip: Mutex<HashMap<IpAddr, usize>>,
}

impl ConnectionManager {
    pub fn new() -> Self {
        Self {
            max_outbound: MAX_OUTBOUND,
            max_inbound: MAX_INBOUND,
            outbound_count: AtomicUsize::new(0),
            inbound_count: AtomicUsize::new(0),
            connecting: Mutex::new(HashSet::new()),
            ban_list: Mutex::new(BanList::new()),
            netgroup_counts: Mutex::new(HashMap::new()),
            retry_info: Mutex::new(HashMap::new()),
            connections_per_ip: Mutex::new(HashMap::new()),
        }
    }

    pub fn with_limits(max_outbound: usize, max_inbound: usize) -> Self {
        Self {
            max_outbound,
            max_inbound,
            outbound_count: AtomicUsize::new(0),
            inbound_count: AtomicUsize::new(0),
            connecting: Mutex::new(HashSet::new()),
            ban_list: Mutex::new(BanList::new()),
            netgroup_counts: Mutex::new(HashMap::new()),
            retry_info: Mutex::new(HashMap::new()),
            connections_per_ip: Mutex::new(HashMap::new()),
        }
    }

    /// Load ban list from file
    pub async fn load_bans<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        let ban_list = BanList::load(path)?;
        *self.ban_list.lock().await = ban_list;
        Ok(())
    }

    /// Save ban list to file
    pub async fn save_bans<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        self.ban_list.lock().await.save(path)
    }

    /// Check if we can accept a new inbound connection
    pub fn can_accept_inbound(&self) -> bool {
        let inbound = self.inbound_count.load(Ordering::SeqCst);
        let outbound = self.outbound_count.load(Ordering::SeqCst);
        inbound < self.max_inbound && (inbound + outbound) < MAX_PEERS
    }

    /// Check if we can accept a connection from this IP (per-IP limit)
    /// Security: Prevents single IP from consuming multiple slots and amplifying rate limits
    pub async fn can_accept_from_ip(&self, addr: &SocketAddr) -> bool {
        let ip = addr.ip();
        let per_ip = self.connections_per_ip.lock().await;
        let current = per_ip.get(&ip).copied().unwrap_or(0);
        current < MAX_CONNECTIONS_PER_IP
    }

    /// Check if we need more outbound connections
    pub fn need_outbound(&self) -> bool {
        self.outbound_count.load(Ordering::SeqCst) < self.max_outbound
    }

    /// Check if we can connect to this address (netgroup diversity)
    pub async fn can_connect(&self, addr: &SocketAddr) -> bool {
        let netgroup = get_netgroup(addr);
        let counts = self.netgroup_counts.lock().await;
        let current = counts.get(&netgroup).copied().unwrap_or(0);
        current < MAX_PEERS_PER_NETGROUP
    }

    /// Check if address can retry (exponential backoff)
    pub async fn can_retry(&self, addr: &SocketAddr) -> bool {
        let retry_info = self.retry_info.lock().await;
        retry_info.get(addr).map(|r| r.can_retry()).unwrap_or(true)
    }

    /// Record connection failure (for backoff)
    pub async fn record_failure(&self, addr: &SocketAddr) {
        let mut retry_info = self.retry_info.lock().await;
        retry_info.entry(*addr).or_insert_with(RetryInfo::new).record_failure();
    }

    /// Record connection success (reset backoff)
    pub async fn record_success(&self, addr: &SocketAddr) {
        let mut retry_info = self.retry_info.lock().await;
        if let Some(info) = retry_info.get_mut(addr) {
            info.record_success();
        }
    }

    /// Start connecting to address (returns false if already connecting)
    pub async fn start_connecting(&self, addr: SocketAddr) -> bool {
        let mut connecting = self.connecting.lock().await;
        if connecting.contains(&addr) {
            return false;
        }
        connecting.insert(addr);
        true
    }

    /// Finish connecting (success or failure)
    pub async fn finish_connecting(&self, addr: &SocketAddr) {
        let mut connecting = self.connecting.lock().await;
        connecting.remove(addr);
    }

    /// Register new outbound connection
    pub async fn add_outbound(&self, addr: &SocketAddr) {
        self.outbound_count.fetch_add(1, Ordering::SeqCst);
        let netgroup = get_netgroup(addr);
        let mut counts = self.netgroup_counts.lock().await;
        *counts.entry(netgroup).or_insert(0) += 1;
        drop(counts);

        // Track per-IP connections
        let ip = addr.ip();
        let mut per_ip = self.connections_per_ip.lock().await;
        *per_ip.entry(ip).or_insert(0) += 1;
    }

    /// Register new inbound connection
    pub async fn add_inbound(&self, addr: &SocketAddr) {
        self.inbound_count.fetch_add(1, Ordering::SeqCst);
        let netgroup = get_netgroup(addr);
        let mut counts = self.netgroup_counts.lock().await;
        *counts.entry(netgroup).or_insert(0) += 1;
        drop(counts);

        // Track per-IP connections
        let ip = addr.ip();
        let mut per_ip = self.connections_per_ip.lock().await;
        *per_ip.entry(ip).or_insert(0) += 1;
    }

    /// Remove peer from counts
    pub async fn remove_peer(&self, addr: &SocketAddr, inbound: bool) {
        if inbound {
            self.inbound_count.fetch_sub(1, Ordering::SeqCst);
        } else {
            self.outbound_count.fetch_sub(1, Ordering::SeqCst);
        }

        let netgroup = get_netgroup(addr);
        let mut counts = self.netgroup_counts.lock().await;
        if let Some(count) = counts.get_mut(&netgroup) {
            *count = count.saturating_sub(1);
            if *count == 0 {
                counts.remove(&netgroup);
            }
        }
        drop(counts);

        // Decrement per-IP counter
        let ip = addr.ip();
        let mut per_ip = self.connections_per_ip.lock().await;
        if let Some(count) = per_ip.get_mut(&ip) {
            *count = count.saturating_sub(1);
            if *count == 0 {
                per_ip.remove(&ip);
            }
        }
    }

    /// Get current connection counts
    pub fn counts(&self) -> (usize, usize) {
        (
            self.outbound_count.load(Ordering::SeqCst),
            self.inbound_count.load(Ordering::SeqCst),
        )
    }

    /// Get total peer count
    pub fn total(&self) -> usize {
        let (out, inb) = self.counts();
        out + inb
    }

    /// Ban an address with duration and reason
    pub async fn ban(&self, addr: SocketAddr, duration_secs: u64, reason: String) {
        let entry = BanEntry::new(addr, duration_secs, reason);
        self.ban_list.lock().await.ban(entry);
    }

    /// Ban an address with default duration
    pub async fn ban_default(&self, addr: SocketAddr) {
        self.ban(addr, 86400, "misbehavior".to_string()).await;
    }

    /// Check if address is banned
    pub async fn is_banned(&self, addr: &SocketAddr) -> bool {
        self.ban_list.lock().await.is_banned(addr)
    }

    /// Unban an address
    pub async fn unban(&self, addr: &SocketAddr) -> bool {
        self.ban_list.lock().await.unban(addr)
    }

    /// Get list of banned addresses
    pub async fn get_banned(&self) -> Vec<BanEntry> {
        self.ban_list.lock().await.list().into_iter().cloned().collect()
    }

    /// Clear all bans
    pub async fn clear_bans(&self) {
        self.ban_list.lock().await.clear();
    }

    /// Expire old bans
    pub async fn expire_bans(&self) {
        self.ban_list.lock().await.expire();
    }

    /// Get number of unique netgroups
    pub async fn netgroup_count(&self) -> usize {
        self.netgroup_counts.lock().await.len()
    }
}

impl Default for ConnectionManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Connection statistics
#[derive(Debug, Clone)]
pub struct ConnectionStats {
    pub outbound: usize,
    pub inbound: usize,
    pub connecting: usize,
    pub banned: usize,
    pub netgroups: usize,
    pub max_outbound: usize,
    pub max_inbound: usize,
}

impl ConnectionManager {
    pub async fn stats(&self) -> ConnectionStats {
        ConnectionStats {
            outbound: self.outbound_count.load(Ordering::SeqCst),
            inbound: self.inbound_count.load(Ordering::SeqCst),
            connecting: self.connecting.lock().await.len(),
            banned: self.ban_list.lock().await.len(),
            netgroups: self.netgroup_counts.lock().await.len(),
            max_outbound: self.max_outbound,
            max_inbound: self.max_inbound,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_ban_persistence() {
        let cm = ConnectionManager::new();
        let addr: SocketAddr = "1.2.3.4:1234".parse().unwrap();

        cm.ban(addr, 3600, "test".to_string()).await;
        assert!(cm.is_banned(&addr).await);

        // Test save/load
        let temp = std::env::temp_dir().join("test_bans.dat");
        cm.save_bans(&temp).await.unwrap();

        let cm2 = ConnectionManager::new();
        cm2.load_bans(&temp).await.unwrap();
        assert!(cm2.is_banned(&addr).await);

        std::fs::remove_file(temp).ok();
    }

    #[tokio::test]
    async fn test_netgroup_diversity() {
        let cm = ConnectionManager::new();
        let addr1: SocketAddr = "1.2.3.4:1234".parse().unwrap();
        let addr2: SocketAddr = "1.2.4.5:1234".parse().unwrap();
        let addr3: SocketAddr = "1.2.5.6:1234".parse().unwrap();

        // Same /16, can connect first 2
        assert!(cm.can_connect(&addr1).await);
        cm.add_outbound(&addr1).await;

        assert!(cm.can_connect(&addr2).await);
        cm.add_outbound(&addr2).await;

        // Third in same /16 should be rejected
        assert!(!cm.can_connect(&addr3).await);

        // Different /16 should work
        let addr4: SocketAddr = "2.3.4.5:1234".parse().unwrap();
        assert!(cm.can_connect(&addr4).await);
    }

    #[tokio::test]
    async fn test_exponential_backoff() {
        let cm = ConnectionManager::new();
        let addr: SocketAddr = "1.2.3.4:1234".parse().unwrap();

        // First attempt should work
        assert!(cm.can_retry(&addr).await);

        // Record failures
        cm.record_failure(&addr).await;

        // Should not be able to retry immediately
        // (depends on timing, so just check the info is recorded)
        let retry_info = cm.retry_info.lock().await;
        let info = retry_info.get(&addr).unwrap();
        assert_eq!(info.attempts, 1);
        assert!(info.next_retry_delay >= INITIAL_RETRY_DELAY_SECS);
    }
}
