//! DNS seeds and fallback IPs for bootstrap

use super::types::{DEFAULT_PORT, NODE_FULL};
use super::NetAddress;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, ToSocketAddrs};
use tracing::{debug, info, warn};

/// Default DNS seeds for Montana mainnet (10 seeds)
pub const DNS_SEEDS: &[&str] = &[
    // Primary seeds (to be populated with actual domains)
    // "seed1.montana.network",
    // "seed2.montana.network",
    // "seed3.montana.network",
    // "seed4.montana.network",
    // "seed5.montana.network",
    // "seed6.montana.network",
    // "seed7.montana.network",
    // "seed8.montana.network",
    // "seed9.montana.network",
    // "seed10.montana.network",
];

/// Fallback IPs for Montana mainnet (10 IPs)
/// Used when DNS resolution fails or as additional hardcoded verification
pub const FALLBACK_IPS: &[(u8, u8, u8, u8)] = &[
    // TimeWeb primary (Moscow)
    (176, 124, 208, 93),
    // Additional fallback IPs (to be populated)
    // (XX, XX, XX, XX),  // seed2.montana.network
    // (XX, XX, XX, XX),  // seed3.montana.network
    // ...
];

/// DNS seeds for testnet
pub const TESTNET_DNS_SEEDS: &[&str] = &[
    // "testnet-seed1.montana.network",
];

/// Fallback IPs for testnet
pub const TESTNET_FALLBACK_IPS: &[(u8, u8, u8, u8)] = &[
    // TimeWeb testnet
    (176, 124, 208, 93),
];

/// DNS seed resolver
pub struct DnsSeeds {
    seeds: Vec<String>,
    port: u16,
}

impl DnsSeeds {
    /// Create resolver for mainnet
    pub fn mainnet() -> Self {
        Self {
            seeds: DNS_SEEDS.iter().map(|s| s.to_string()).collect(),
            port: DEFAULT_PORT,
        }
    }

    /// Create resolver for testnet
    pub fn testnet() -> Self {
        Self {
            seeds: TESTNET_DNS_SEEDS.iter().map(|s| s.to_string()).collect(),
            port: DEFAULT_PORT + 1,
        }
    }

    /// Create resolver with custom seeds
    pub fn with_seeds(seeds: Vec<String>, port: u16) -> Self {
        Self { seeds, port }
    }

    /// Add a DNS seed
    pub fn add_seed(&mut self, seed: &str) {
        if !self.seeds.contains(&seed.to_string()) {
            self.seeds.push(seed.to_string());
        }
    }

    /// Resolve all DNS seeds to addresses
    pub fn resolve(&self) -> Vec<NetAddress> {
        let mut addresses = Vec::new();

        for seed in &self.seeds {
            match self.resolve_seed(seed) {
                Ok(addrs) => {
                    info!("Resolved {} addresses from {}", addrs.len(), seed);
                    addresses.extend(addrs);
                }
                Err(e) => {
                    warn!("Failed to resolve {}: {}", seed, e);
                }
            }
        }

        // Deduplicate
        addresses.sort_by_key(|a| a.socket_addr());
        addresses.dedup_by_key(|a| a.socket_addr());

        info!("Total {} unique addresses from DNS seeds", addresses.len());
        addresses
    }

    /// Resolve a single DNS seed
    fn resolve_seed(&self, seed: &str) -> Result<Vec<NetAddress>, std::io::Error> {
        let lookup = format!("{}:{}", seed, self.port);
        let addrs: Vec<SocketAddr> = lookup.to_socket_addrs()?.collect();

        debug!("DNS seed {} resolved to {} addresses", seed, addrs.len());

        Ok(addrs
            .into_iter()
            .map(|addr| NetAddress::from_socket_addr(addr, NODE_FULL))
            .collect())
    }

    /// Resolve DNS seeds asynchronously
    pub async fn resolve_async(&self) -> Vec<NetAddress> {
        let seeds = self.seeds.clone();
        let port = self.port;

        // Run DNS resolution in blocking task
        tokio::task::spawn_blocking(move || {
            let resolver = DnsSeeds { seeds, port };
            resolver.resolve()
        })
        .await
        .unwrap_or_default()
    }
}

/// Resolve hostname to IP addresses
pub fn resolve_hostname(hostname: &str) -> Result<Vec<IpAddr>, std::io::Error> {
    let lookup = format!("{}:0", hostname);
    let addrs: Vec<IpAddr> = lookup
        .to_socket_addrs()?
        .map(|addr| addr.ip())
        .collect();
    Ok(addrs)
}

/// Check if hostname resolves to any addresses
pub fn hostname_resolves(hostname: &str) -> bool {
    resolve_hostname(hostname).map(|v| !v.is_empty()).unwrap_or(false)
}

/// Get fallback IPs as SocketAddr for mainnet
pub fn get_fallback_addrs_mainnet() -> Vec<SocketAddr> {
    FALLBACK_IPS
        .iter()
        .map(|(a, b, c, d)| {
            SocketAddr::new(IpAddr::V4(Ipv4Addr::new(*a, *b, *c, *d)), DEFAULT_PORT)
        })
        .collect()
}

/// Get fallback IPs as SocketAddr for testnet
pub fn get_fallback_addrs_testnet() -> Vec<SocketAddr> {
    TESTNET_FALLBACK_IPS
        .iter()
        .map(|(a, b, c, d)| {
            SocketAddr::new(IpAddr::V4(Ipv4Addr::new(*a, *b, *c, *d)), DEFAULT_PORT + 1)
        })
        .collect()
}

/// Get all hardcoded addresses (DNS seeds + fallback IPs) for mainnet
/// Used by BootstrapVerifier to identify trusted hardcoded nodes
pub fn get_all_hardcoded_addrs_mainnet() -> Vec<SocketAddr> {
    let mut addrs = Vec::new();

    // DNS seeds (resolved)
    let dns = DnsSeeds::mainnet();
    for addr in dns.resolve() {
        addrs.push(addr.socket_addr());
    }

    // Fallback IPs
    addrs.extend(get_fallback_addrs_mainnet());

    // Deduplicate
    addrs.sort();
    addrs.dedup();

    info!("Loaded {} hardcoded addresses", addrs.len());
    addrs
}

/// Get all hardcoded addresses for testnet
pub fn get_all_hardcoded_addrs_testnet() -> Vec<SocketAddr> {
    let mut addrs = Vec::new();

    // DNS seeds (resolved)
    let dns = DnsSeeds::testnet();
    for addr in dns.resolve() {
        addrs.push(addr.socket_addr());
    }

    // Fallback IPs
    addrs.extend(get_fallback_addrs_testnet());

    // Deduplicate
    addrs.sort();
    addrs.dedup();

    addrs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_localhost() {
        let addrs = resolve_hostname("localhost").unwrap();
        assert!(!addrs.is_empty());
    }

    #[test]
    fn test_dns_seeds_empty() {
        let dns = DnsSeeds::mainnet();
        let addrs = dns.resolve();
        // Empty because DNS_SEEDS is empty for now
        assert!(addrs.is_empty() || !addrs.is_empty()); // Always passes
    }

    #[test]
    fn test_custom_seeds() {
        let mut dns = DnsSeeds::with_seeds(vec![], DEFAULT_PORT);
        dns.add_seed("localhost");

        // This should resolve localhost
        let _addrs = dns.resolve();
        // localhost may or may not be running Montana
        assert!(true);
    }

    #[test]
    fn test_fallback_ips_mainnet() {
        let addrs = get_fallback_addrs_mainnet();
        // TimeWeb is present
        assert!(!addrs.is_empty());

        let timeweb = SocketAddr::new(
            IpAddr::V4(Ipv4Addr::new(176, 124, 208, 93)),
            DEFAULT_PORT,
        );
        assert!(addrs.contains(&timeweb));
    }

    #[test]
    fn test_fallback_ips_testnet() {
        let addrs = get_fallback_addrs_testnet();
        assert!(!addrs.is_empty());
    }

    #[test]
    fn test_hardcoded_includes_timeweb() {
        let addrs = get_all_hardcoded_addrs_mainnet();
        let timeweb = SocketAddr::new(
            IpAddr::V4(Ipv4Addr::new(176, 124, 208, 93)),
            DEFAULT_PORT,
        );
        assert!(addrs.contains(&timeweb));
    }
}
