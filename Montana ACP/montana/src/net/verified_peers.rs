//! Presence-Verified Addresses — P2P discovery через консенсус
//!
//! Адрес считается "verified" если:
//! 1. Узел по этому адресу прошёл handshake с ML-DSA pubkey
//! 2. Этот pubkey имеет presence proof в цепи за последние τ₃ (14 дней)
//!
//! # Security Properties
//!
//! - **Eclipse resistance**: Атакующий не может заполнить verified list без
//!   реального presence в цепи (требует Adaptive Cooldown)
//! - **Sybil resistance**: Каждый verified peer прошёл cooldown период
//! - **Poisoning resistance**: Нельзя подделать binding — требуется handshake

use crate::types::{Hash, PublicKey};
use sha3::{Digest, Sha3_256};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::time::Instant;

/// τ₃ в τ₂ слайсах (14 дней = 2016 τ₂)
const TAU3_IN_TAU2: u64 = 2016;

/// Максимум verified peers (memory bound: ~20MB при 10K peers)
const MAX_VERIFIED_PEERS: usize = 10_000;

/// Binding между pubkey и socket address
#[derive(Debug, Clone)]
pub struct PeerBinding {
    /// ML-DSA-65 public key (1952 bytes)
    pub pubkey: PublicKey,
    /// Socket address (IP:port)
    pub addr: SocketAddr,
    /// Когда создан binding (handshake time)
    pub bound_at: Instant,
    /// Последний τ₂ с presence proof (0 = never seen in chain)
    pub last_presence_tau2: u64,
    /// Cumulative weight узла (из цепи)
    pub weight: u64,
}

impl PeerBinding {
    /// Создать новый binding
    pub fn new(pubkey: PublicKey, addr: SocketAddr) -> Self {
        Self {
            pubkey,
            addr,
            bound_at: Instant::now(),
            last_presence_tau2: 0,
            weight: 0,
        }
    }

    /// Проверить, верифицирован ли узел (presence в последние τ₃)
    #[inline]
    pub fn is_verified(&self, current_tau2: u64) -> bool {
        if self.last_presence_tau2 == 0 {
            return false;
        }
        current_tau2.saturating_sub(self.last_presence_tau2) <= TAU3_IN_TAU2
    }

    /// Обновить presence info
    pub fn update_presence(&mut self, tau2_index: u64, weight: u64) {
        self.last_presence_tau2 = tau2_index;
        self.weight = weight;
    }
}

/// Менеджер verified peers
pub struct VerifiedPeers {
    /// pubkey_hash → PeerBinding
    bindings: HashMap<Hash, PeerBinding>,
    /// addr → pubkey_hash (reverse lookup)
    addr_to_pubkey: HashMap<SocketAddr, Hash>,
    /// Текущий τ₂ индекс (обновляется из цепи)
    current_tau2: u64,
}

impl VerifiedPeers {
    pub fn new() -> Self {
        Self {
            bindings: HashMap::with_capacity(1000),
            addr_to_pubkey: HashMap::with_capacity(1000),
            current_tau2: 0,
        }
    }

    /// Создать binding при успешном handshake
    pub fn bind(&mut self, pubkey: PublicKey, addr: SocketAddr) {
        // Eviction если переполнено
        if self.bindings.len() >= MAX_VERIFIED_PEERS {
            self.evict_oldest_unverified();
        }

        let pubkey_hash = hash_pubkey(&pubkey);

        // Удалить старый binding для этого addr если есть
        if let Some(old_hash) = self.addr_to_pubkey.remove(&addr) {
            self.bindings.remove(&old_hash);
        }

        // Удалить старый binding для этого pubkey если есть (IP change)
        if let Some(old_binding) = self.bindings.remove(&pubkey_hash) {
            self.addr_to_pubkey.remove(&old_binding.addr);
        }

        let binding = PeerBinding::new(pubkey, addr);
        self.bindings.insert(pubkey_hash, binding);
        self.addr_to_pubkey.insert(addr, pubkey_hash);
    }

    /// Удалить binding при disconnect
    pub fn unbind(&mut self, addr: &SocketAddr) {
        if let Some(pubkey_hash) = self.addr_to_pubkey.remove(addr) {
            self.bindings.remove(&pubkey_hash);
        }
    }

    /// Обновить presence info из цепи
    pub fn update_presence(&mut self, pubkey: &PublicKey, tau2_index: u64, weight: u64) {
        let pubkey_hash = hash_pubkey(pubkey);
        if let Some(binding) = self.bindings.get_mut(&pubkey_hash) {
            binding.update_presence(tau2_index, weight);
        }
    }

    /// Batch update из нового слайса
    pub fn update_from_slice(&mut self, tau2_index: u64, presences: &[(PublicKey, u64)]) {
        self.current_tau2 = tau2_index;
        for (pubkey, weight) in presences {
            self.update_presence(pubkey, tau2_index, *weight);
        }
    }

    /// Обновить текущий τ₂ (вызывается при новом слайсе)
    pub fn set_current_tau2(&mut self, tau2: u64) {
        self.current_tau2 = tau2;
    }

    /// Получить текущий τ₂
    pub fn current_tau2(&self) -> u64 {
        self.current_tau2
    }

    /// Получить verified peers отсортированные по весу (больше = лучше)
    pub fn get_verified(&self) -> Vec<SocketAddr> {
        let mut verified: Vec<_> = self
            .bindings
            .values()
            .filter(|b| b.is_verified(self.current_tau2))
            .collect();

        // Сортировка по весу (descending)
        verified.sort_by(|a, b| b.weight.cmp(&a.weight));

        verified.into_iter().map(|b| b.addr).collect()
    }

    /// Получить verified peers исключая уже подключённые
    pub fn get_verified_excluding(&self, connected: &[SocketAddr]) -> Vec<SocketAddr> {
        let mut verified: Vec<_> = self
            .bindings
            .values()
            .filter(|b| b.is_verified(self.current_tau2))
            .filter(|b| !connected.contains(&b.addr))
            .collect();

        verified.sort_by(|a, b| b.weight.cmp(&a.weight));
        verified.into_iter().map(|b| b.addr).collect()
    }

    /// Проверить, verified ли конкретный адрес
    pub fn is_verified(&self, addr: &SocketAddr) -> bool {
        self.addr_to_pubkey
            .get(addr)
            .and_then(|h| self.bindings.get(h))
            .map(|b| b.is_verified(self.current_tau2))
            .unwrap_or(false)
    }

    /// Получить binding по адресу
    pub fn get_binding(&self, addr: &SocketAddr) -> Option<&PeerBinding> {
        self.addr_to_pubkey
            .get(addr)
            .and_then(|h| self.bindings.get(h))
    }

    /// Количество всех bindings
    pub fn len(&self) -> usize {
        self.bindings.len()
    }

    /// Проверка на пустоту
    pub fn is_empty(&self) -> bool {
        self.bindings.is_empty()
    }

    /// Количество verified peers
    pub fn verified_count(&self) -> usize {
        self.bindings
            .values()
            .filter(|b| b.is_verified(self.current_tau2))
            .count()
    }

    /// Статистика
    pub fn stats(&self) -> VerifiedPeersStats {
        let verified = self.verified_count();
        VerifiedPeersStats {
            total_bindings: self.bindings.len(),
            verified,
            unverified: self.bindings.len() - verified,
            current_tau2: self.current_tau2,
        }
    }

    /// Evict oldest unverified binding (LRU)
    fn evict_oldest_unverified(&mut self) {
        // Найти самый старый unverified binding
        let oldest = self
            .bindings
            .iter()
            .filter(|(_, b)| !b.is_verified(self.current_tau2))
            .min_by_key(|(_, b)| b.bound_at);

        if let Some((hash, binding)) = oldest {
            let hash = *hash;
            let addr = binding.addr;
            self.bindings.remove(&hash);
            self.addr_to_pubkey.remove(&addr);
        } else {
            // Все verified — удаляем с наименьшим весом
            let lowest_weight = self
                .bindings
                .iter()
                .min_by_key(|(_, b)| b.weight);

            if let Some((hash, binding)) = lowest_weight {
                let hash = *hash;
                let addr = binding.addr;
                self.bindings.remove(&hash);
                self.addr_to_pubkey.remove(&addr);
            }
        }
    }
}

impl Default for VerifiedPeers {
    fn default() -> Self {
        Self::new()
    }
}

/// Статистика verified peers
#[derive(Debug, Clone)]
pub struct VerifiedPeersStats {
    pub total_bindings: usize,
    pub verified: usize,
    pub unverified: usize,
    pub current_tau2: u64,
}

/// Hash pubkey для использования как ключ
#[inline]
fn hash_pubkey(pubkey: &PublicKey) -> Hash {
    let mut hasher = Sha3_256::new();
    hasher.update(pubkey);
    hasher.finalize().into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{IpAddr, Ipv4Addr};

    fn make_addr(port: u16) -> SocketAddr {
        SocketAddr::new(IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4)), port)
    }

    fn make_pubkey(seed: u8) -> PublicKey {
        vec![seed; 1952]
    }

    #[test]
    fn test_bind_unbind() {
        let mut vp = VerifiedPeers::new();

        let pubkey = make_pubkey(1);
        let addr = make_addr(19333);

        vp.bind(pubkey.clone(), addr);
        assert_eq!(vp.len(), 1);
        assert!(!vp.is_verified(&addr)); // No presence yet

        vp.unbind(&addr);
        assert_eq!(vp.len(), 0);
    }

    #[test]
    fn test_verification() {
        let mut vp = VerifiedPeers::new();

        let pubkey = make_pubkey(1);
        let addr = make_addr(19333);

        vp.bind(pubkey.clone(), addr);
        vp.set_current_tau2(1000);

        // Not verified without presence
        assert!(!vp.is_verified(&addr));

        // Add presence
        vp.update_presence(&pubkey, 999, 100);
        assert!(vp.is_verified(&addr));

        // Still verified within τ₃
        vp.set_current_tau2(999 + TAU3_IN_TAU2);
        assert!(vp.is_verified(&addr));

        // Expired after τ₃
        vp.set_current_tau2(999 + TAU3_IN_TAU2 + 1);
        assert!(!vp.is_verified(&addr));
    }

    #[test]
    fn test_get_verified_sorted_by_weight() {
        let mut vp = VerifiedPeers::new();
        vp.set_current_tau2(1000);

        // Add 3 peers with different weights
        for i in 1..=3u8 {
            let pubkey = make_pubkey(i);
            let addr = make_addr(19333 + i as u16);
            vp.bind(pubkey.clone(), addr);
            vp.update_presence(&pubkey, 999, i as u64 * 100);
        }

        let verified = vp.get_verified();
        assert_eq!(verified.len(), 3);

        // Should be sorted by weight descending (300, 200, 100)
        assert_eq!(verified[0].port(), 19336); // weight 300
        assert_eq!(verified[1].port(), 19335); // weight 200
        assert_eq!(verified[2].port(), 19334); // weight 100
    }

    #[test]
    fn test_eviction() {
        let mut vp = VerifiedPeers::new();
        vp.set_current_tau2(1000);

        // Fill to MAX (each pubkey must be unique)
        for i in 0..MAX_VERIFIED_PEERS {
            // Create unique pubkey by embedding i as bytes
            let mut pubkey = vec![0u8; 1952];
            pubkey[0..8].copy_from_slice(&(i as u64).to_le_bytes());
            // Unique port (i + 1 to avoid port 0)
            let addr = SocketAddr::new(
                IpAddr::V4(Ipv4Addr::new(
                    ((i >> 16) & 0xFF) as u8,
                    ((i >> 8) & 0xFF) as u8,
                    (i & 0xFF) as u8,
                    1,
                )),
                ((i % 65534) + 1) as u16,
            );
            vp.bind(pubkey, addr);
        }

        assert_eq!(vp.len(), MAX_VERIFIED_PEERS);

        // Add one more — should trigger eviction
        let new_pubkey = vec![0xFFu8; 1952];
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(255, 255, 255, 1)), 65000);
        vp.bind(new_pubkey, addr);

        assert_eq!(vp.len(), MAX_VERIFIED_PEERS);
    }

    #[test]
    fn test_ip_change() {
        let mut vp = VerifiedPeers::new();

        let pubkey = make_pubkey(1);
        let addr1 = make_addr(19333);
        let addr2 = make_addr(19334);

        // Bind to first addr
        vp.bind(pubkey.clone(), addr1);
        assert_eq!(vp.len(), 1);
        assert!(vp.get_binding(&addr1).is_some());

        // Same pubkey, different addr — should update
        vp.bind(pubkey.clone(), addr2);
        assert_eq!(vp.len(), 1);
        assert!(vp.get_binding(&addr1).is_none());
        assert!(vp.get_binding(&addr2).is_some());
    }
}
