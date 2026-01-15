use crate::types::{Hash, PublicKey, Signature};
use pqcrypto_dilithium::dilithium3 as dilithium;
use pqcrypto_traits::sign::{PublicKey as PkTrait, DetachedSignature, SecretKey as SkTrait};
use sha3::{Digest, Sha3_256};
use thiserror::Error;

pub const MLDSA65_PUBKEY_SIZE: usize = 1952;
pub const MLDSA65_SIG_SIZE: usize = 3293;
pub const MLDSA65_SECRET_SIZE: usize = 4000;

pub type MlDsa65PublicKey = [u8; MLDSA65_PUBKEY_SIZE];
pub type MlDsa65Signature = Vec<u8>;

pub mod mldsa {
    pub use super::{
        MlDsa65PublicKey, MlDsa65Signature,
        MLDSA65_PUBKEY_SIZE, MLDSA65_SIG_SIZE, MLDSA65_SECRET_SIZE,
        verify_mldsa65, sign_mldsa65,
    };
}

#[derive(Error, Debug)]
pub enum CryptoError {
    #[error("invalid signature")]
    InvalidSignature,
    #[error("invalid public key")]
    InvalidPublicKey,
}

pub struct Keypair {
    pub public: PublicKey,
    secret: dilithium::SecretKey,
}

impl Keypair {
    pub fn generate() -> Self {
        let (pk, sk) = dilithium::keypair();
        Self {
            public: pk.as_bytes().to_vec(),
            secret: sk,
        }
    }

    pub fn sign(&self, message: &[u8]) -> Signature {
        let sig = dilithium::detached_sign(message, &self.secret);
        sig.as_bytes().to_vec()
    }

    pub fn public_key(&self) -> &PublicKey {
        &self.public
    }
}

pub fn verify(pubkey: &PublicKey, message: &[u8], signature: &Signature) -> Result<(), CryptoError> {
    let pk = dilithium::PublicKey::from_bytes(pubkey).map_err(|_| CryptoError::InvalidPublicKey)?;
    let sig = dilithium::DetachedSignature::from_bytes(signature).map_err(|_| CryptoError::InvalidSignature)?;
    dilithium::verify_detached_signature(&sig, message, &pk).map_err(|_| CryptoError::InvalidSignature)
}

pub fn sha3(data: &[u8]) -> Hash {
    Sha3_256::digest(data).into()
}

pub fn sha3_concat(a: &[u8], b: &[u8]) -> Hash {
    let mut hasher = Sha3_256::new();
    hasher.update(a);
    hasher.update(b);
    hasher.finalize().into()
}

pub fn merkle_root(leaves: &[Hash]) -> Hash {
    if leaves.is_empty() {
        return [0u8; 32];
    }
    if leaves.len() == 1 {
        return leaves[0];
    }

    let mut level: Vec<Hash> = leaves.to_vec();

    while level.len() > 1 {
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        for chunk in level.chunks(2) {
            if chunk.len() == 2 {
                next.push(sha3_concat(&chunk[0], &chunk[1]));
            } else {
                next.push(sha3_concat(&chunk[0], &chunk[0]));
            }
        }
        level = next;
    }

    level[0]
}

pub fn lottery_seed(prev_hash: &Hash, tau2_index: u64) -> Hash {
    let mut data = prev_hash.to_vec();
    data.extend(&tau2_index.to_le_bytes());
    sha3(&data)
}

pub fn select_pool(seed: &Hash) -> u8 {
    seed[0] % 100
}

pub fn select_winner(seed: &Hash, weights: &[(PublicKey, u64)]) -> Option<PublicKey> {
    if weights.is_empty() {
        return None;
    }

    let total: u64 = weights.iter().map(|(_, w)| w).sum();
    if total == 0 {
        return None;
    }

    let target = u64::from_le_bytes(seed[0..8].try_into().unwrap()) % total;

    let mut cumulative = 0u64;
    for (pubkey, weight) in weights {
        cumulative += weight;
        if cumulative > target {
            return Some(pubkey.clone());
        }
    }

    Some(weights.last().unwrap().0.clone())
}

pub fn verify_mldsa65(pubkey: &MlDsa65PublicKey, message: &[u8], signature: &[u8]) -> bool {
    let pk = match dilithium::PublicKey::from_bytes(pubkey) {
        Ok(pk) => pk,
        Err(_) => return false,
    };
    let sig = match dilithium::DetachedSignature::from_bytes(signature) {
        Ok(sig) => sig,
        Err(_) => return false,
    };
    dilithium::verify_detached_signature(&sig, message, &pk).is_ok()
}

pub fn sign_mldsa65(secret_key: &[u8], message: &[u8]) -> Option<MlDsa65Signature> {
    let sk = dilithium::SecretKey::from_bytes(secret_key).ok()?;
    let sig = dilithium::detached_sign(message, &sk);
    Some(sig.as_bytes().to_vec())
}

pub fn generate_mldsa65_keypair() -> (MlDsa65PublicKey, Vec<u8>) {
    let (pk, sk) = dilithium::keypair();
    let mut pubkey = [0u8; MLDSA65_PUBKEY_SIZE];
    pubkey.copy_from_slice(pk.as_bytes());
    (pubkey, sk.as_bytes().to_vec())
}
