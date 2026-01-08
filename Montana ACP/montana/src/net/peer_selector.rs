//! Unified peer selection с трёхуровневой системой доверия
//!
//! # Trust Levels
//!
//! | Level | Name         | Source                    | Trust    |
//! |-------|--------------|---------------------------|----------|
//! | 0     | Trusted Core | Hardcoded ML-DSA nodes    | Maximum  |
//! | 1     | Verified     | Presence proof in chain   | High     |
//! | 2     | Gossip       | Addr messages (AddrMan)   | Low      |
//!
//! # Selection Algorithm
//!
//! 1. If no peers connected → use Trusted Core (bootstrap)
//! 2. If verified available → 70% chance to select from verified
//! 3. Fallback → gossip (AddrMan)

use super::addrman::AddrMan;
use super::hardcoded_identity::{get_hardcoded_nodes, HardcodedNode};
use super::verified_peers::VerifiedPeers;
use rand::Rng;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Уровни доверия для peer selection
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrustLevel {
    /// Level 0: Hardcoded nodes (bootstrap)
    TrustedCore,
    /// Level 1: Presence-verified (consensus-backed)
    Verified,
    /// Level 2: Gossip addresses (unverified)
    Gossip,
}

impl TrustLevel {
    /// Числовой приоритет (меньше = лучше)
    pub fn priority(&self) -> u8 {
        match self {
            TrustLevel::TrustedCore => 0,
            TrustLevel::Verified => 1,
            TrustLevel::Gossip => 2,
        }
    }
}

/// Результат selection
#[derive(Debug, Clone)]
pub struct SelectedPeer {
    pub addr: SocketAddr,
    pub trust_level: TrustLevel,
}

/// Unified peer selector
pub struct PeerSelector {
    /// Level 0: Hardcoded trusted nodes
    trusted_core: Vec<HardcodedNode>,
    /// Level 1: Presence-verified peers
    verified: Arc<RwLock<VerifiedPeers>>,
    /// Level 2: Gossip-based AddrMan
    addrman: Arc<RwLock<AddrMan>>,
}

impl PeerSelector {
    pub fn new(
        verified: Arc<RwLock<VerifiedPeers>>,
        addrman: Arc<RwLock<AddrMan>>,
        testnet: bool,
    ) -> Self {
        let trusted_core = get_hardcoded_nodes(testnet).to_vec();

        Self {
            trusted_core,
            verified,
            addrman,
        }
    }

    /// Выбрать peer для подключения
    ///
    /// Приоритет:
    /// 1. Если нет соединений → Trusted Core (bootstrap)
    /// 2. Verified peers (70% если доступны)
    /// 3. Gossip peers (30% или fallback)
    pub async fn select(&self, connected: &[SocketAddr]) -> Option<SelectedPeer> {
        // Bootstrap mode: если нет соединений, используем Trusted Core
        if connected.is_empty() {
            if let Some(addr) = self.select_trusted_core(connected) {
                return Some(SelectedPeer {
                    addr,
                    trust_level: TrustLevel::TrustedCore,
                });
            }
        }

        // Normal selection
        let verified_peers = {
            let vp = self.verified.read().await;
            vp.get_verified_excluding(connected)
        };

        // 70% шанс выбрать verified если доступны
        if !verified_peers.is_empty() && rand::thread_rng().gen_bool(0.7) {
            let idx = rand::thread_rng().gen_range(0..verified_peers.len());
            return Some(SelectedPeer {
                addr: verified_peers[idx],
                trust_level: TrustLevel::Verified,
            });
        }

        // Fallback на gossip (AddrMan)
        {
            let mut am = self.addrman.write().await;
            if let Some(addr) = am.select() {
                let socket = addr.socket_addr();
                if !connected.contains(&socket) {
                    return Some(SelectedPeer {
                        addr: socket,
                        trust_level: TrustLevel::Gossip,
                    });
                }
            }
        }

        // Последний fallback — verified (если 70% не сработал)
        if !verified_peers.is_empty() {
            let idx = rand::thread_rng().gen_range(0..verified_peers.len());
            return Some(SelectedPeer {
                addr: verified_peers[idx],
                trust_level: TrustLevel::Verified,
            });
        }

        // Совсем крайний случай — Trusted Core
        self.select_trusted_core(connected).map(|addr| SelectedPeer {
            addr,
            trust_level: TrustLevel::TrustedCore,
        })
    }

    /// Выбрать несколько peers для подключения
    pub async fn select_multiple(
        &self,
        count: usize,
        connected: &[SocketAddr],
    ) -> Vec<SelectedPeer> {
        let mut result = Vec::with_capacity(count);
        let mut excluded: Vec<SocketAddr> = connected.to_vec();

        for _ in 0..count {
            if let Some(peer) = self.select(&excluded).await {
                excluded.push(peer.addr);
                result.push(peer);
            } else {
                break;
            }
        }

        result
    }

    /// Выбрать из Trusted Core
    fn select_trusted_core(&self, connected: &[SocketAddr]) -> Option<SocketAddr> {
        self.trusted_core
            .iter()
            .map(|n| n.addr)
            .find(|addr| !connected.contains(addr))
    }

    /// Получить все Trusted Core адреса
    pub fn get_trusted_core(&self) -> Vec<SocketAddr> {
        self.trusted_core.iter().map(|n| n.addr).collect()
    }

    /// Проверить, является ли адрес Trusted Core
    pub fn is_trusted_core(&self, addr: &SocketAddr) -> bool {
        self.trusted_core.iter().any(|n| &n.addr == addr)
    }

    /// Получить trust level для адреса
    pub async fn get_trust_level(&self, addr: &SocketAddr) -> TrustLevel {
        if self.is_trusted_core(addr) {
            return TrustLevel::TrustedCore;
        }

        let verified = self.verified.read().await;
        if verified.is_verified(addr) {
            return TrustLevel::Verified;
        }

        TrustLevel::Gossip
    }

    /// Статистика
    pub async fn stats(&self) -> PeerSelectorStats {
        let verified = self.verified.read().await;
        let addrman = self.addrman.read().await;
        let (gossip_new, gossip_tried) = addrman.size();

        PeerSelectorStats {
            trusted_core: self.trusted_core.len(),
            verified: verified.verified_count(),
            verified_total: verified.len(),
            gossip_new,
            gossip_tried,
        }
    }
}

/// Статистика peer selector
#[derive(Debug, Clone)]
pub struct PeerSelectorStats {
    /// Количество hardcoded nodes
    pub trusted_core: usize,
    /// Количество verified peers (presence в последние τ₃)
    pub verified: usize,
    /// Всего bindings (verified + unverified)
    pub verified_total: usize,
    /// Gossip: new addresses
    pub gossip_new: usize,
    /// Gossip: tried addresses
    pub gossip_tried: usize,
}

impl PeerSelectorStats {
    /// Общее количество доступных peers
    pub fn total_available(&self) -> usize {
        self.trusted_core + self.verified + self.gossip_new + self.gossip_tried
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::net::types::NetAddress;
    use std::net::{IpAddr, Ipv4Addr};

    fn make_addr(port: u16) -> SocketAddr {
        SocketAddr::new(IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8)), port)
    }

    #[tokio::test]
    async fn test_bootstrap_uses_trusted_core() {
        let verified = Arc::new(RwLock::new(VerifiedPeers::new()));
        let addrman = Arc::new(RwLock::new(AddrMan::new()));
        let selector = PeerSelector::new(verified, addrman, false);

        // No connected peers → should use trusted core
        let selected = selector.select(&[]).await;
        assert!(selected.is_some());
        assert_eq!(selected.unwrap().trust_level, TrustLevel::TrustedCore);
    }

    #[tokio::test]
    async fn test_prefers_verified() {
        let verified = Arc::new(RwLock::new(VerifiedPeers::new()));
        let addrman = Arc::new(RwLock::new(AddrMan::new()));

        // Add verified peer
        {
            let mut vp = verified.write().await;
            vp.set_current_tau2(1000);
            let pubkey = vec![1u8; 1952];
            vp.bind(pubkey.clone(), make_addr(19333));
            vp.update_presence(&pubkey, 999, 100);
        }

        // Add gossip peer
        {
            let mut am = addrman.write().await;
            let addr = NetAddress::new(IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4)), 19334, 1);
            am.add(addr, None);
        }

        let selector = PeerSelector::new(verified, addrman, false);

        // With one connection, should prefer verified (statistically)
        let mut verified_count = 0;
        let connected = vec![make_addr(1)]; // Dummy connected

        for _ in 0..100 {
            if let Some(peer) = selector.select(&connected).await {
                if peer.trust_level == TrustLevel::Verified {
                    verified_count += 1;
                }
            }
        }

        // Should be around 70% verified
        assert!(verified_count > 50, "Expected ~70% verified, got {}", verified_count);
    }
}
