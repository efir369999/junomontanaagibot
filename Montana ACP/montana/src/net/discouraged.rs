//! Discouraged peer tracking using rolling bloom filter
//!
//! Uses probabilistic data structure for memory-efficient tracking
//! of misbehaving peers with soft punishment (deprioritization).

use siphasher::sip::SipHasher24;
use std::hash::Hasher;
use std::net::SocketAddr;

/// Rolling bloom filter for discouraged addresses
/// False positives are acceptable (probabilistic structure)
/// Enumeration hidden by design (privacy protection)
pub struct DiscouragedFilter {
    /// Filter data
    data: Vec<u64>,
    /// Number of hash functions
    n_hash: u32,
    /// Number of elements added in current generation
    n_elements: u32,
    /// Maximum elements before rolling
    max_elements: u32,
    /// Current generation (for rolling)
    generation: u32,
    /// Random tweak for hash
    tweak: u64,
}

impl DiscouragedFilter {
    /// Create new filter with expected capacity and false positive rate
    pub fn new(max_elements: u32, fp_rate: f64) -> Self {
        // Calculate optimal filter size
        let n_filter_bytes = (-1.0 / (2.0_f64.ln().powi(2)) * max_elements as f64 * fp_rate.ln())
            .ceil() as usize;
        let n_filter_bytes = n_filter_bytes.max(1);

        // Round up to multiple of 8 (u64)
        let n_u64 = n_filter_bytes.div_ceil(8);

        // Calculate optimal number of hash functions
        let n_hash = (n_filter_bytes as f64 * 8.0 / max_elements as f64 * 2.0_f64.ln())
            .round() as u32;
        let n_hash = n_hash.clamp(1, 50);

        Self {
            data: vec![0; n_u64 * 2], // 2x for rolling
            n_hash,
            n_elements: 0,
            max_elements,
            generation: 1,
            tweak: rand::random(),
        }
    }

    /// Create with default parameters (50000 elements, 0.000001 FP rate)
    pub fn default_params() -> Self {
        Self::new(50000, 0.000001)
    }

    /// Add address to discouraged set
    pub fn add(&mut self, addr: &SocketAddr) {
        // Check if need to roll
        if self.n_elements >= self.max_elements {
            self.roll();
        }

        let key = addr_to_key(addr);
        let half = self.data.len() / 2;

        for i in 0..self.n_hash {
            let bit = self.hash(i, &key);
            let word = bit / 64;
            let bit_in_word = bit % 64;

            // Set bit in current generation
            if self.generation % 2 == 1 {
                self.data[word] |= 1 << bit_in_word;
            } else {
                self.data[half + word] |= 1 << bit_in_word;
            }
        }

        self.n_elements += 1;
    }

    /// Check if address is discouraged
    pub fn contains(&self, addr: &SocketAddr) -> bool {
        let key = addr_to_key(addr);
        let half = self.data.len() / 2;

        for i in 0..self.n_hash {
            let bit = self.hash(i, &key);
            let word = bit / 64;
            let bit_in_word = bit % 64;

            // Check both generations
            let in_gen1 = (self.data[word] >> bit_in_word) & 1 == 1;
            let in_gen2 = (self.data[half + word] >> bit_in_word) & 1 == 1;

            if !in_gen1 && !in_gen2 {
                return false;
            }
        }

        true
    }

    /// Roll the filter (start new generation)
    fn roll(&mut self) {
        let half = self.data.len() / 2;

        // Clear the older generation
        if self.generation % 2 == 1 {
            // Clear second half (will become new current)
            for i in half..self.data.len() {
                self.data[i] = 0;
            }
        } else {
            // Clear first half
            for i in 0..half {
                self.data[i] = 0;
            }
        }

        self.generation += 1;
        self.n_elements = 0;
        self.tweak = rand::random();
    }

    /// Hash function for bloom filter
    fn hash(&self, n: u32, key: &[u8]) -> usize {
        let mut hasher = SipHasher24::new_with_keys(
            self.tweak,
            (n as u64) << 32 | self.generation as u64,
        );
        hasher.write(key);
        (hasher.finish() as usize) % (self.data.len() / 2 * 64)
    }

    /// Get approximate number of discouraged addresses
    pub fn size(&self) -> u32 {
        self.n_elements
    }

    /// Reset filter
    pub fn reset(&mut self) {
        for v in &mut self.data {
            *v = 0;
        }
        self.n_elements = 0;
        self.generation = 1;
        self.tweak = rand::random();
    }
}

impl Default for DiscouragedFilter {
    fn default() -> Self {
        Self::default_params()
    }
}

fn addr_to_key(addr: &SocketAddr) -> Vec<u8> {
    let mut key = Vec::with_capacity(18);
    match addr.ip() {
        std::net::IpAddr::V4(ip) => {
            key.push(4);
            key.extend_from_slice(&ip.octets());
        }
        std::net::IpAddr::V6(ip) => {
            key.push(6);
            key.extend_from_slice(&ip.octets());
        }
    }
    key.extend_from_slice(&addr.port().to_le_bytes());
    key
}

/// Combined ban and discourage management
pub struct PeerReputation {
    /// Discouraged (soft punishment)
    pub discouraged: DiscouragedFilter,
}

impl PeerReputation {
    pub fn new() -> Self {
        Self {
            discouraged: DiscouragedFilter::default_params(),
        }
    }

    /// Discourage a peer (soft punishment)
    pub fn discourage(&mut self, addr: &SocketAddr) {
        tracing::info!("Discouraging peer {}", addr);
        self.discouraged.add(addr);
    }

    /// Check if peer is discouraged
    pub fn is_discouraged(&self, addr: &SocketAddr) -> bool {
        self.discouraged.contains(addr)
    }

    /// Get discouraged count
    pub fn discouraged_count(&self) -> u32 {
        self.discouraged.size()
    }

    /// Reset all reputation data
    pub fn reset(&mut self) {
        self.discouraged.reset();
    }
}

impl Default for PeerReputation {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_discouraged_filter() {
        let mut filter = DiscouragedFilter::new(100, 0.001);

        let addr: SocketAddr = "1.2.3.4:1234".parse().unwrap();

        assert!(!filter.contains(&addr));
        filter.add(&addr);
        assert!(filter.contains(&addr));
    }

    #[test]
    fn test_discouraged_filter_false_positive_rate() {
        let mut filter = DiscouragedFilter::new(1000, 0.01);

        // Add some addresses
        for i in 0..500 {
            let addr: SocketAddr = format!("1.2.{}.{}:1234", i / 256, i % 256).parse().unwrap();
            filter.add(&addr);
        }

        // Check false positives on addresses we didn't add
        let mut false_positives = 0;
        for i in 500..1000 {
            let addr: SocketAddr = format!("1.2.{}.{}:1234", i / 256, i % 256).parse().unwrap();
            if filter.contains(&addr) {
                false_positives += 1;
            }
        }

        // Should be roughly 1% false positive rate (allow some margin)
        assert!(false_positives < 50, "Too many false positives: {}", false_positives);
    }

    #[test]
    fn test_discouraged_filter_rolling() {
        let mut filter = DiscouragedFilter::new(10, 0.01);

        // Fill filter
        for i in 0..10 {
            let addr: SocketAddr = format!("1.1.1.{}:1234", i).parse().unwrap();
            filter.add(&addr);
        }

        // Add more to trigger roll
        for i in 10..20 {
            let addr: SocketAddr = format!("1.1.1.{}:1234", i).parse().unwrap();
            filter.add(&addr);
        }

        // Recent additions should be present
        let addr: SocketAddr = "1.1.1.19:1234".parse().unwrap();
        assert!(filter.contains(&addr));
    }

    #[test]
    fn test_peer_reputation() {
        let mut rep = PeerReputation::new();
        let addr: SocketAddr = "1.2.3.4:1234".parse().unwrap();

        assert!(!rep.is_discouraged(&addr));
        rep.discourage(&addr);
        assert!(rep.is_discouraged(&addr));
    }
}
