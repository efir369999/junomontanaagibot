//! Address manager with cryptographic bucket system

use super::types::{AddressInfo, NetAddress};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha20Rng;
use serde::{Deserialize, Serialize};
use siphasher::sip::SipHasher24;
use std::collections::{HashMap, HashSet};
use std::hash::Hasher;
use std::net::{IpAddr, SocketAddr};
use std::path::Path;

// Bucket configuration (based on Bitcoin Core)
const NEW_BUCKET_COUNT: usize = 1024;
const TRIED_BUCKET_COUNT: usize = 256;
const BUCKET_SIZE: usize = 64;
const MAX_RETRIES: u32 = 3;
const HORIZON_DAYS: u64 = 30;

// Maximum serialized size for AddrMan (security limit for file load)
// New: 1024*64 entries, Tried: 256*64 entries, ~100 bytes each = ~8MB
// Using 16MB as safe upper bound
const MAX_ADDRMAN_FILE_SIZE: u64 = 16 * 1024 * 1024;

/// Address manager with bucketed storage
#[derive(Debug, Serialize, Deserialize)]
pub struct AddrMan {
    /// Random key for bucket assignment (prevents attacker from predicting buckets)
    #[serde(with = "key_serde")]
    key: [u8; 32],

    /// New addresses (received, pending verification)
    new_table: Vec<Option<usize>>, // bucket -> addr index

    /// Tried addresses (successfully connected)
    tried_table: Vec<Option<usize>>, // bucket -> addr index

    /// All known addresses
    addrs: HashMap<usize, AddressInfo>,

    /// Address to index mapping
    addr_to_idx: HashMap<SocketAddr, usize>,

    /// Next address index
    next_idx: usize,

    /// Number of addresses in new table
    new_count: usize,

    /// Number of addresses in tried table
    tried_count: usize,

    /// Currently connected peers (not serialized)
    #[serde(skip)]
    connected: HashSet<SocketAddr>,

    /// Our own local addresses
    #[serde(skip)]
    local_addresses: Vec<NetAddress>,
}

mod key_serde {
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    pub fn serialize<S>(key: &[u8; 32], serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        key.to_vec().serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<[u8; 32], D::Error>
    where
        D: Deserializer<'de>,
    {
        let vec = Vec::<u8>::deserialize(deserializer)?;
        vec.try_into().map_err(|_| serde::de::Error::custom("invalid key length"))
    }
}

impl AddrMan {
    pub fn new() -> Self {
        let mut key = [0u8; 32];
        rand::thread_rng().fill(&mut key);

        Self {
            key,
            new_table: vec![None; NEW_BUCKET_COUNT * BUCKET_SIZE],
            tried_table: vec![None; TRIED_BUCKET_COUNT * BUCKET_SIZE],
            addrs: HashMap::new(),
            addr_to_idx: HashMap::new(),
            next_idx: 0,
            new_count: 0,
            tried_count: 0,
            connected: HashSet::new(),
            local_addresses: Vec::new(),
        }
    }

    /// Load from file with size limit
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self, std::io::Error> {
        let data = std::fs::read(&path)?;

        // Security: reject oversized files before deserialization
        if data.len() as u64 > MAX_ADDRMAN_FILE_SIZE {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("addrman file too large: {} bytes", data.len()),
            ));
        }

        // Use standard bincode (matches save() serialization format)
        bincode::deserialize(&data)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))
    }

    /// Save to file
    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        let data = bincode::serialize(self).map_err(|e| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, e)
        })?;
        std::fs::write(path, data)
    }

    /// Add a new address (heard from network)
    pub fn add(&mut self, addr: NetAddress, source: Option<SocketAddr>) -> bool {
        let socket_addr = addr.socket_addr();

        // Skip if already known
        if self.addr_to_idx.contains_key(&socket_addr) {
            return false;
        }

        // Skip non-routable
        if !addr.is_routable() {
            return false;
        }

        // SECURITY: Reject future timestamps (Time-Travel Poisoning defense)
        // Allow 10 min clock skew, reject anything beyond
        let now = crate::types::now();
        if addr.timestamp > now.saturating_add(600) {
            return false;
        }

        // Create address info
        let info = AddressInfo::new(addr.clone(), source);

        // Get bucket position
        let bucket = self.get_new_bucket(&socket_addr, source.as_ref());
        let pos = self.get_bucket_position(&socket_addr, bucket, true);
        let idx = bucket * BUCKET_SIZE + pos;

        // Check if slot is occupied
        if let Some(existing_idx) = self.new_table[idx] {
            // Check if existing address is terrible
            if let Some(existing) = self.addrs.get(&existing_idx)
                && !existing.is_terrible()
            {
                return false; // Keep existing good address
            }
            // Remove existing
            self.remove_from_new(existing_idx);
        }

        // Add new address
        let addr_idx = self.next_idx;
        self.next_idx += 1;

        self.addrs.insert(addr_idx, info);
        self.addr_to_idx.insert(socket_addr, addr_idx);
        self.new_table[idx] = Some(addr_idx);
        self.new_count += 1;

        true
    }

    /// Mark address as successfully connected (move to tried)
    pub fn mark_good(&mut self, addr: &SocketAddr) {
        let Some(&addr_idx) = self.addr_to_idx.get(addr) else {
            return;
        };

        // Update address info
        if let Some(info) = self.addrs.get_mut(&addr_idx) {
            info.mark_success();
        }

        // Check if already in tried
        if self.is_in_tried(addr_idx) {
            return;
        }

        // Remove from new
        self.remove_from_new(addr_idx);

        // Add to tried
        let bucket = self.get_tried_bucket(addr);
        let pos = self.get_bucket_position(addr, bucket, false);
        let idx = bucket * BUCKET_SIZE + pos;

        // Handle collision
        if let Some(existing_idx) = self.tried_table[idx] {
            // Move existing back to new
            self.move_to_new(existing_idx);
        }

        self.tried_table[idx] = Some(addr_idx);
        self.tried_count += 1;
    }

    /// Mark address as connection attempt
    pub fn mark_attempt(&mut self, addr: &SocketAddr) {
        if let Some(&idx) = self.addr_to_idx.get(addr)
            && let Some(info) = self.addrs.get_mut(&idx)
        {
            info.mark_attempt();
        }
    }

    /// Select an address to connect to (50/50 new vs tried)
    pub fn select(&mut self) -> Option<NetAddress> {
        self.select_inner(false)
    }

    /// Select an address to connect to with option for new only
    pub fn select_with_option(&mut self, new_only: bool) -> Option<NetAddress> {
        self.select_inner(new_only)
    }

    fn select_inner(&mut self, new_only: bool) -> Option<NetAddress> {
        let mut rng = ChaCha20Rng::from_entropy();

        // 50% chance to try new address (or 100% if new_only)
        let use_new = new_only || rng.gen_bool(0.5);

        if use_new && self.new_count > 0 {
            self.select_from_new(&mut rng)
        } else if self.tried_count > 0 {
            self.select_from_tried(&mut rng)
        } else if self.new_count > 0 {
            self.select_from_new(&mut rng)
        } else {
            None
        }
    }

    /// Get random addresses for sharing (addr relay)
    pub fn get_addr(&self, max_count: usize) -> Vec<NetAddress> {
        let mut rng = ChaCha20Rng::from_entropy();
        let mut result = Vec::with_capacity(max_count);

        // Prefer tried addresses (more reliable)
        let tried_pct = 0.7;
        let tried_count = (max_count as f64 * tried_pct) as usize;

        // Collect from tried
        for (_, info) in self.addrs.iter().filter(|(idx, _)| self.is_in_tried(**idx)) {
            if result.len() >= tried_count {
                break;
            }
            if !info.is_terrible() {
                result.push(info.addr.clone());
            }
        }

        // Fill rest from new
        for (_, info) in self.addrs.iter() {
            if result.len() >= max_count {
                break;
            }
            if !info.is_terrible() && !result.iter().any(|a| a.socket_addr() == info.addr.socket_addr()) {
                result.push(info.addr.clone());
            }
        }

        // Shuffle
        for i in (1..result.len()).rev() {
            let j = rng.gen_range(0..=i);
            result.swap(i, j);
        }

        result.truncate(max_count);
        result
    }

    /// Get count of known addresses
    pub fn size(&self) -> (usize, usize) {
        (self.new_count, self.tried_count)
    }

    /// Check if address is known
    pub fn contains(&self, addr: &SocketAddr) -> bool {
        self.addr_to_idx.contains_key(addr)
    }

    /// Add seed address (bypasses routable check for bootstrap/testing)
    pub fn add_seed(&mut self, addr: NetAddress) -> bool {
        let socket_addr = addr.socket_addr();

        // Skip if already connected or known
        if self.connected.contains(&socket_addr) || self.addr_to_idx.contains_key(&socket_addr) {
            return false;
        }

        // Create address info
        let info = AddressInfo::new(addr.clone(), None);

        // Use proper bucket placement (same as regular add, just skip routable check)
        let bucket = self.get_new_bucket(&socket_addr, None);
        let pos = self.get_bucket_position(&socket_addr, bucket, true);
        let idx = bucket * BUCKET_SIZE + pos;

        // Handle collision - seeds replace existing
        if let Some(existing_idx) = self.new_table[idx] {
            self.remove_from_new(existing_idx);
        }

        // Add to address map
        let addr_idx = self.next_idx;
        self.next_idx += 1;

        self.addrs.insert(addr_idx, info);
        self.addr_to_idx.insert(socket_addr, addr_idx);
        self.new_table[idx] = Some(addr_idx);
        self.new_count += 1;

        true
    }

    /// Add local address
    pub fn add_local(&mut self, addr: NetAddress) {
        if !self.local_addresses.iter().any(|a| a.socket_addr() == addr.socket_addr()) {
            self.local_addresses.push(addr);
        }
    }

    /// Get local addresses
    pub fn get_local(&self) -> &[NetAddress] {
        &self.local_addresses
    }

    /// Mark address as connected (move to tried)
    pub fn mark_connected(&mut self, addr: &SocketAddr) {
        self.connected.insert(*addr);
        self.mark_good(addr);
    }

    /// Mark connection attempt failed
    pub fn mark_failed(&mut self, addr: &SocketAddr) {
        self.mark_attempt(addr);

        // Remove if too many failures
        if let Some(&idx) = self.addr_to_idx.get(addr) {
            if let Some(info) = self.addrs.get(&idx) {
                if info.attempts >= MAX_RETRIES {
                    self.remove(addr);
                }
            }
        }
    }

    /// Mark address as disconnected
    pub fn mark_disconnected(&mut self, addr: &SocketAddr) {
        self.connected.remove(addr);
    }

    /// Remove address completely
    pub fn remove(&mut self, addr: &SocketAddr) {
        if let Some(&idx) = self.addr_to_idx.get(addr) {
            // Remove from new table
            self.remove_from_new(idx);

            // Remove from tried table
            for slot in self.tried_table.iter_mut() {
                if *slot == Some(idx) {
                    *slot = None;
                    self.tried_count = self.tried_count.saturating_sub(1);
                    break;
                }
            }

            // Remove from maps
            self.addrs.remove(&idx);
            self.addr_to_idx.remove(addr);
        }
    }

    /// Expire old addresses that were never successfully connected
    pub fn expire(&mut self) {
        let now = crate::types::now();
        let horizon = now.saturating_sub(HORIZON_DAYS * 24 * 60 * 60);

        let to_remove: Vec<SocketAddr> = self.addrs
            .iter()
            .filter(|(_, info)| info.addr.timestamp < horizon && info.last_success == 0)
            .filter_map(|(idx, _)| {
                self.addr_to_idx.iter()
                    .find(|(_, i)| **i == *idx)
                    .map(|(addr, _)| *addr)
            })
            .collect();

        for addr in to_remove {
            self.remove(&addr);
        }
    }

    /// Add multiple addresses (from addr message)
    pub fn add_many(&mut self, addrs: Vec<NetAddress>, source: SocketAddr) -> usize {
        let mut added = 0;
        for addr in addrs {
            if self.add(addr, Some(source)) {
                added += 1;
            }
        }
        added
    }

    /// Get total number of known addresses
    pub fn len(&self) -> usize {
        self.addrs.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.addrs.is_empty()
    }

    /// Get statistics
    pub fn stats(&self) -> AddrManStats {
        AddrManStats {
            total: self.addrs.len(),
            new: self.new_count,
            tried: self.tried_count,
            connected: self.connected.len(),
        }
    }

    // Internal helper methods

    fn get_new_bucket(&self, addr: &SocketAddr, source: Option<&SocketAddr>) -> usize {
        let mut hasher = SipHasher24::new_with_key(&self.key[..16].try_into().unwrap());

        // Hash: key || netgroup || source_netgroup
        hasher.write(&get_netgroup_bytes(addr));
        if let Some(src) = source {
            hasher.write(&get_netgroup_bytes(src));
        }

        (hasher.finish() as usize) % NEW_BUCKET_COUNT
    }

    fn get_tried_bucket(&self, addr: &SocketAddr) -> usize {
        let mut hasher = SipHasher24::new_with_key(&self.key[..16].try_into().unwrap());

        // Hash: key || addr || netgroup
        hasher.write(&addr_to_bytes(addr));
        hasher.write(&get_netgroup_bytes(addr));

        (hasher.finish() as usize) % TRIED_BUCKET_COUNT
    }

    fn get_bucket_position(&self, addr: &SocketAddr, bucket: usize, is_new: bool) -> usize {
        let mut hasher = SipHasher24::new_with_key(&self.key[16..].try_into().unwrap());

        hasher.write(&addr_to_bytes(addr));
        hasher.write(&bucket.to_le_bytes());
        hasher.write(&[if is_new { 1 } else { 0 }]);

        (hasher.finish() as usize) % BUCKET_SIZE
    }

    fn is_in_tried(&self, addr_idx: usize) -> bool {
        self.tried_table.contains(&Some(addr_idx))
    }

    fn remove_from_new(&mut self, addr_idx: usize) {
        for slot in self.new_table.iter_mut() {
            if *slot == Some(addr_idx) {
                *slot = None;
                self.new_count = self.new_count.saturating_sub(1);
                return;
            }
        }
    }

    fn move_to_new(&mut self, addr_idx: usize) {
        // Remove from tried
        for slot in self.tried_table.iter_mut() {
            if *slot == Some(addr_idx) {
                *slot = None;
                self.tried_count = self.tried_count.saturating_sub(1);
                break;
            }
        }

        // Add to new
        if let Some(info) = self.addrs.get(&addr_idx) {
            let socket_addr = info.addr.socket_addr();
            let bucket = self.get_new_bucket(&socket_addr, info.source.as_ref());
            let pos = self.get_bucket_position(&socket_addr, bucket, true);
            let idx = bucket * BUCKET_SIZE + pos;

            if self.new_table[idx].is_none() {
                self.new_table[idx] = Some(addr_idx);
                self.new_count += 1;
            }
        }
    }

    fn select_from_new(&self, rng: &mut ChaCha20Rng) -> Option<NetAddress> {
        let now = crate::types::now();
        let horizon = now.saturating_sub(HORIZON_DAYS * 24 * 60 * 60);

        // Fast path for sparse tables: iterate directly when few addresses
        // Random sampling has low hit rate with sparse data
        if self.new_count <= 10 {
            for slot in self.new_table.iter() {
                if let Some(addr_idx) = slot
                    && let Some(info) = self.addrs.get(addr_idx)
                {
                    let socket_addr = info.addr.socket_addr();
                    if self.connected.contains(&socket_addr) {
                        continue;
                    }
                    if info.is_terrible() || info.addr.timestamp < horizon {
                        continue;
                    }
                    if info.attempts >= MAX_RETRIES {
                        continue;
                    }
                    return Some(info.addr.clone());
                }
            }
            return None;
        }

        // Normal random sampling for dense tables
        for _ in 0..1000 {
            let bucket = rng.gen_range(0..NEW_BUCKET_COUNT);
            let pos = rng.gen_range(0..BUCKET_SIZE);
            let idx = bucket * BUCKET_SIZE + pos;

            if let Some(addr_idx) = self.new_table[idx]
                && let Some(info) = self.addrs.get(&addr_idx)
            {
                let socket_addr = info.addr.socket_addr();

                // Skip if already connected
                if self.connected.contains(&socket_addr) {
                    continue;
                }
                // Skip terrible or too old
                if info.is_terrible() || info.addr.timestamp < horizon {
                    continue;
                }
                // Skip if too many recent attempts
                if info.attempts >= MAX_RETRIES {
                    continue;
                }
                return Some(info.addr.clone());
            }
        }
        None
    }

    fn select_from_tried(&self, rng: &mut ChaCha20Rng) -> Option<NetAddress> {
        // Fast path for sparse tables
        if self.tried_count <= 10 {
            for slot in self.tried_table.iter() {
                if let Some(addr_idx) = slot
                    && let Some(info) = self.addrs.get(addr_idx)
                {
                    let socket_addr = info.addr.socket_addr();
                    if self.connected.contains(&socket_addr) {
                        continue;
                    }
                    if info.is_terrible() {
                        continue;
                    }
                    return Some(info.addr.clone());
                }
            }
            return None;
        }

        // Normal random sampling
        for _ in 0..1000 {
            let bucket = rng.gen_range(0..TRIED_BUCKET_COUNT);
            let pos = rng.gen_range(0..BUCKET_SIZE);
            let idx = bucket * BUCKET_SIZE + pos;

            if let Some(addr_idx) = self.tried_table[idx]
                && let Some(info) = self.addrs.get(&addr_idx)
            {
                let socket_addr = info.addr.socket_addr();

                // Skip if already connected
                if self.connected.contains(&socket_addr) {
                    continue;
                }
                if info.is_terrible() {
                    continue;
                }
                return Some(info.addr.clone());
            }
        }
        None
    }
}

impl Default for AddrMan {
    fn default() -> Self {
        Self::new()
    }
}

/// Address manager statistics
#[derive(Debug, Clone)]
pub struct AddrManStats {
    pub total: usize,
    pub new: usize,
    pub tried: usize,
    pub connected: usize,
}

fn get_netgroup_bytes(addr: &SocketAddr) -> [u8; 4] {
    match addr.ip() {
        IpAddr::V4(ip) => {
            let octets = ip.octets();
            [octets[0], octets[1], 0, 0]
        }
        IpAddr::V6(ip) => {
            let segments = ip.segments();
            let b0 = (segments[0] >> 8) as u8;
            let b1 = (segments[0] & 0xff) as u8;
            let b2 = (segments[1] >> 8) as u8;
            let b3 = (segments[1] & 0xff) as u8;
            [b0, b1, b2, b3]
        }
    }
}

fn addr_to_bytes(addr: &SocketAddr) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(18);
    match addr.ip() {
        IpAddr::V4(ip) => {
            bytes.push(4);
            bytes.extend_from_slice(&ip.octets());
        }
        IpAddr::V6(ip) => {
            bytes.push(6);
            bytes.extend_from_slice(&ip.octets());
        }
    }
    bytes.extend_from_slice(&addr.port().to_le_bytes());
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;

    #[test]
    fn test_addrman_add() {
        let mut am = AddrMan::new();

        let addr = NetAddress::new(IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4)), 19333, 1);
        assert!(am.add(addr.clone(), None));

        // Duplicate should fail
        assert!(!am.add(addr, None));

        let (new, tried) = am.size();
        assert_eq!(new, 1);
        assert_eq!(tried, 0);
    }

    #[test]
    fn test_addrman_mark_good() {
        let mut am = AddrMan::new();

        let addr = NetAddress::new(IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4)), 19333, 1);
        am.add(addr.clone(), None);

        let (new, tried) = am.size();
        assert_eq!(new, 1);
        assert_eq!(tried, 0);

        am.mark_good(&addr.socket_addr());

        let (new, tried) = am.size();
        assert_eq!(new, 0);
        assert_eq!(tried, 1);
    }

    #[test]
    fn test_addrman_select() {
        let mut am = AddrMan::new();

        // Add addresses and mark some as good (move to tried table)
        for i in 1..50 {
            let addr = NetAddress::new(
                IpAddr::V4(Ipv4Addr::new(i, i, i, i)),
                19333,
                1,
            );
            am.add(addr.clone(), None);
            // Mark every 5th as good (move to tried)
            if i % 5 == 0 {
                am.mark_good(&addr.socket_addr());
            }
        }

        // Try multiple selections (random algorithm may miss on first try)
        let mut found = false;
        for _ in 0..100 {
            if am.select().is_some() {
                found = true;
                break;
            }
        }
        assert!(found, "Should be able to select an address after multiple tries");
    }

    #[test]
    fn test_addrman_bucket_distribution() {
        let mut am = AddrMan::new();

        // Add many addresses from different /16 subnets
        for i in 1..100 {
            let addr = NetAddress::new(
                IpAddr::V4(Ipv4Addr::new(i, i, 1, 1)),
                19333,
                1,
            );
            am.add(addr, None);
        }

        let (new, _) = am.size();
        // Should have added most of them (some might collide)
        assert!(new >= 90);
    }
}
