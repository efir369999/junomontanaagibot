//! Unit tests for crypto module
//!
//! Tests ML-DSA-65 signing and SHA3-256 hashing.
//!
//! NOTE: Lottery functions (merkle_root, lottery_seed, select_pool) were removed
//! due to grinding vulnerability. See consensus.rs for specification.

use montana::{sha3, Keypair, verify};

#[test]
fn test_sha3_deterministic() {
    let hash1 = sha3(b"test");
    let hash2 = sha3(b"test");
    assert_eq!(hash1, hash2);

    let hash3 = sha3(b"different");
    assert_ne!(hash1, hash3);
}

#[test]
fn test_sha3_length() {
    let hash = sha3(b"any input");
    assert_eq!(hash.len(), 32); // SHA3-256 = 32 bytes
}

#[test]
fn test_sign_verify() {
    let kp = Keypair::generate();
    let msg = b"test message";
    let sig = kp.sign(msg);
    assert!(verify(&kp.public, msg, &sig).is_ok());
}

#[test]
fn test_sign_verify_wrong_message() {
    let kp = Keypair::generate();
    let msg = b"original message";
    let sig = kp.sign(msg);

    // Verification with different message should fail
    let wrong_msg = b"tampered message";
    assert!(verify(&kp.public, wrong_msg, &sig).is_err());
}

#[test]
fn test_sign_verify_wrong_key() {
    let kp1 = Keypair::generate();
    let kp2 = Keypair::generate();
    let msg = b"test message";
    let sig = kp1.sign(msg);

    // Verification with different public key should fail
    assert!(verify(&kp2.public, msg, &sig).is_err());
}

#[test]
fn test_keypair_unique() {
    let kp1 = Keypair::generate();
    let kp2 = Keypair::generate();

    // Two generated keypairs should be different
    assert_ne!(kp1.public, kp2.public);
}
