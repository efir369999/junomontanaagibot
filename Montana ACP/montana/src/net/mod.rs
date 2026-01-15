//! P2P networking layer

pub mod serde_safe;
pub mod addrman;
pub mod bootstrap;
pub mod connection;
pub mod discouraged;
pub mod dns;
pub mod encrypted;
pub mod eviction;
pub mod feeler;
pub mod hardcoded_identity;
pub mod inventory;
pub mod message;
pub mod noise;
pub mod peer;
pub mod peer_selector;
pub mod protocol;
pub mod rate_limit;
pub mod startup;
pub mod subnet;
pub mod sync;
pub mod types;
pub mod verification;
pub mod verified_peers;

// Re-exports
pub use addrman::{AddrMan, AddrManStats};
pub use connection::{BanEntry, BanList, ConnectionManager, ConnectionStats, RetryInfo};
pub use discouraged::{DiscouragedFilter, PeerReputation};
pub use dns::{
    get_all_hardcoded_addrs_mainnet, get_all_hardcoded_addrs_testnet, get_fallback_addrs_mainnet,
    get_fallback_addrs_testnet, DnsSeeds, FALLBACK_IPS, TESTNET_FALLBACK_IPS,
};
pub use eviction::{select_peer_to_evict, EvictionCandidate, EvictionStats};
pub use feeler::{AddrResponseCache, FeelerManager};
pub use inventory::Inventory;
pub use message::{
    Message, Addrs, InvItems, Headers, PresenceProofs, LocatorHashes, Signature,
    MAX_AUTH_CHALLENGE_SIZE, MAX_AUTH_RESPONSE_SIZE, MAX_SIGNED_ADDR_SIZE,
};
pub use peer::{Peer, PeerInfo};
pub use protocol::{NetConfig, NetError, NetEvent, Network};
pub use rate_limit::{
    FlowControl, PeerRateLimits, TokenBucket,
    // Erebus protection: two-tier adaptive subnet rate limiting
    GlobalSubnetLimiter, GlobalSubnetStats,
    AdaptiveSubnetLimiter, AdaptiveSubnetStats, AdaptiveTierStats,
};
pub use sync::{
    HeaderSync, LateSignatureBuffer, LateSignatureStats, OrphanPool, SliceDownloader, SyncStats,
};
pub use bootstrap::{
    BootstrapError, BootstrapResult, BootstrapVerifier, PeerChainInfo, PeerHistory, PeerSource,
};
pub use subnet::{
    SubnetReputation, SubnetTracker, MAX_NODES_PER_SUBNET, MIN_DIVERSE_SUBNETS,
    REPUTATION_SNAPSHOT_INTERVAL,
};
pub use startup::{
    StartupError, StartupResult, StartupVerifier,
    needs_verification, verification_type,
};
pub use verification::{VerificationClient, VerificationError, VerificationResult};
pub use hardcoded_identity::{
    get_hardcoded_addrs, get_hardcoded_nodes, get_hardcoded_pubkey, is_hardcoded_addr,
    verify_hardcoded_response, HardcodedAuthError, HardcodedNode,
    Challenge, CHALLENGE_SIZE, MAINNET_HARDCODED, TESTNET_HARDCODED,
};
pub use noise::{
    HandshakeState, NoiseError, NoiseTransport, StaticKeypair,
    NOISE_PROTOCOL_NAME, MAX_NOISE_MESSAGE_SIZE,
};
pub use encrypted::{
    EncryptedError, EncryptedReader, EncryptedStream, EncryptedWriter,
    load_or_generate_keypair, pubkey_fingerprint,
    NOISE_HANDSHAKE_TIMEOUT_SECS,
};
pub use types::*;
pub use serde_safe::{
    BoundedVec, BoundedBytes, from_bytes, to_bytes,
    MAX_ADDRS, MAX_INV_ITEMS, MAX_HEADERS, MAX_PRESENCE_PROOFS,
    MAX_LOCATOR_HASHES, MAX_SIGNATURE_BYTES, MAX_TX_INPUTS, MAX_TX_OUTPUTS,
};
pub use verified_peers::{PeerBinding, VerifiedPeers, VerifiedPeersStats};
pub use peer_selector::{PeerSelector, PeerSelectorStats, SelectedPeer, TrustLevel};
