//! Short-lived connections to verify addresses

use super::addrman::AddrMan;
use std::net::SocketAddr;
use std::time::{Duration, Instant};
use tokio::net::TcpStream;
use tokio::sync::Mutex;
use tokio::time::timeout;

/// Feeler connection interval (2 minutes like Bitcoin Core)
pub const FEELER_INTERVAL: Duration = Duration::from_secs(120);

/// Feeler connection timeout
pub const FEELER_TIMEOUT: Duration = Duration::from_secs(10);

/// Maximum concurrent feelers
pub const MAX_CONCURRENT_FEELERS: usize = 1;

/// Feeler connection manager
pub struct FeelerManager {
    /// Last feeler time
    last_feeler: Mutex<Instant>,
    /// Active feeler count
    active_count: Mutex<usize>,
}

impl FeelerManager {
    pub fn new() -> Self {
        Self {
            last_feeler: Mutex::new(Instant::now() - FEELER_INTERVAL),
            active_count: Mutex::new(0),
        }
    }

    /// Check if we should attempt a feeler connection
    pub async fn should_attempt(&self) -> bool {
        let last = *self.last_feeler.lock().await;
        let active = *self.active_count.lock().await;

        last.elapsed() >= FEELER_INTERVAL && active < MAX_CONCURRENT_FEELERS
    }

    /// Start a feeler connection attempt
    pub async fn start_feeler(&self) -> bool {
        let mut active = self.active_count.lock().await;
        if *active >= MAX_CONCURRENT_FEELERS {
            return false;
        }
        *active += 1;
        *self.last_feeler.lock().await = Instant::now();
        true
    }

    /// End a feeler connection attempt
    pub async fn end_feeler(&self) {
        let mut active = self.active_count.lock().await;
        *active = active.saturating_sub(1);
    }

    /// Perform feeler connection to test address
    pub async fn test_address(
        &self,
        addr: SocketAddr,
        addrman: &Mutex<AddrMan>,
    ) -> bool {
        if !self.start_feeler().await {
            return false;
        }

        // Record attempt
        addrman.lock().await.mark_attempt(&addr);

        // Try to connect
        let result = timeout(FEELER_TIMEOUT, TcpStream::connect(addr)).await;

        let success = match result {
            Ok(Ok(_stream)) => {
                // Connection successful - mark as good
                tracing::debug!("Feeler to {} succeeded", addr);
                addrman.lock().await.mark_good(&addr);
                true
            }
            Ok(Err(e)) => {
                // Connection failed
                tracing::debug!("Feeler to {} failed: {}", addr, e);
                false
            }
            Err(_) => {
                // Timeout
                tracing::debug!("Feeler to {} timed out", addr);
                false
            }
        };

        self.end_feeler().await;
        success
    }

    /// Select and test a random address from AddrMan
    pub async fn run_feeler(&self, addrman: &Mutex<AddrMan>) -> Option<SocketAddr> {
        if !self.should_attempt().await {
            return None;
        }

        // Select from new table only (purpose of feeler)
        let addr = {
            let mut am = addrman.lock().await;
            am.select_with_option(true).map(|a| a.socket_addr())
        };

        if let Some(addr) = addr {
            self.test_address(addr, addrman).await;
            Some(addr)
        } else {
            None
        }
    }
}

impl Default for FeelerManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Address response cache for privacy protection
/// Prevents attackers from scraping addresses in real-time
pub struct AddrResponseCache {
    /// Cached responses per (network, local_socket) pair
    cache: Mutex<std::collections::HashMap<CacheKey, CachedResponse>>,
    /// Cache TTL
    ttl: Duration,
}

#[derive(Debug, Clone, Hash, Eq, PartialEq)]
struct CacheKey {
    network: String,
    local_port: u16,
}

#[derive(Debug, Clone)]
struct CachedResponse {
    addresses: Vec<super::types::NetAddress>,
    created_at: Instant,
}

impl AddrResponseCache {
    pub fn new() -> Self {
        Self {
            cache: Mutex::new(std::collections::HashMap::new()),
            // 5 minute cache
            ttl: Duration::from_secs(300),
        }
    }

    /// Get cached addresses or generate new response
    pub async fn get_or_create(
        &self,
        network: &str,
        local_port: u16,
        addrman: &Mutex<AddrMan>,
        max_count: usize,
    ) -> Vec<super::types::NetAddress> {
        let key = CacheKey {
            network: network.to_string(),
            local_port,
        };

        let mut cache = self.cache.lock().await;

        // Check if valid cached response exists
        if let Some(cached) = cache.get(&key)
            && cached.created_at.elapsed() < self.ttl
        {
            return cached.addresses.clone();
        }

        // Generate new response
        let addresses = addrman.lock().await.get_addr(max_count);

        // Cache it
        cache.insert(key, CachedResponse {
            addresses: addresses.clone(),
            created_at: Instant::now(),
        });

        addresses
    }

    /// Clear expired entries
    pub async fn clear_expired(&self) {
        let mut cache = self.cache.lock().await;
        cache.retain(|_, v| v.created_at.elapsed() < self.ttl);
    }

    /// Clear all cache
    pub async fn clear(&self) {
        self.cache.lock().await.clear();
    }
}

impl Default for AddrResponseCache {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_feeler_manager_rate_limit() {
        let fm = FeelerManager::new();

        // First should be allowed (after initial interval passes)
        assert!(fm.start_feeler().await);

        // Second should be blocked (already one active)
        assert!(!fm.start_feeler().await);

        // End first
        fm.end_feeler().await;

        // But rate limited by time
        assert!(!fm.should_attempt().await);
    }

    #[tokio::test]
    async fn test_addr_cache() {
        let cache = AddrResponseCache::new();
        let addrman = Mutex::new(AddrMan::new());

        // Add some addresses
        {
            let mut am = addrman.lock().await;
            for i in 1..10 {
                let addr = super::super::types::NetAddress::new(
                    std::net::IpAddr::V4(std::net::Ipv4Addr::new(i, i, i, i)),
                    19333,
                    1,
                );
                am.add(addr, None);
            }
        }

        // First call should generate
        let addrs1 = cache.get_or_create("ipv4", 19333, &addrman, 5).await;

        // Second call should return cached
        let addrs2 = cache.get_or_create("ipv4", 19333, &addrman, 5).await;

        // Should be same addresses
        assert_eq!(addrs1.len(), addrs2.len());
    }
}
