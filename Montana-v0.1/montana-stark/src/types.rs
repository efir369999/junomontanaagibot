//! Types for Montana STARK VDF proofs

use serde::{Deserialize, Serialize};
use thiserror::Error;
use winterfell::Proof;

/// Errors that can occur during VDF proof operations
#[derive(Error, Debug)]
pub enum VdfError {
    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("Proof generation failed: {0}")]
    ProofGenerationFailed(String),

    #[error("Proof verification failed: {0}")]
    VerificationFailed(String),

    #[error("Serialization error: {0}")]
    SerializationError(String),

    #[error("Invalid checkpoint count: expected {expected}, got {got}")]
    InvalidCheckpointCount { expected: usize, got: usize },
}

/// STARK proof for VDF computation
///
/// Proves that output = H^T(input) where H = SHAKE256
#[derive(Clone, Serialize, Deserialize)]
pub struct VdfProof {
    /// The raw STARK proof bytes
    pub proof_bytes: Vec<u8>,

    /// Number of iterations proven
    pub iterations: u64,

    /// Checkpoint interval used during proof generation
    pub checkpoint_interval: u64,

    /// Security level (bits)
    pub security_bits: u8,
}

impl VdfProof {
    /// Create a new VDF proof from winterfell Proof
    pub fn from_stark_proof(
        proof: Proof,
        iterations: u64,
        checkpoint_interval: u64,
        security_bits: u8,
    ) -> Result<Self, VdfError> {
        let proof_bytes = proof.to_bytes();

        Ok(Self {
            proof_bytes,
            iterations,
            checkpoint_interval,
            security_bits,
        })
    }

    /// Serialize proof to bytes
    pub fn to_bytes(&self) -> Result<Vec<u8>, VdfError> {
        bincode::serialize(self)
            .map_err(|e| VdfError::SerializationError(e.to_string()))
    }

    /// Deserialize proof from bytes
    pub fn from_bytes(data: &[u8]) -> Result<Self, VdfError> {
        bincode::deserialize(data)
            .map_err(|e| VdfError::SerializationError(e.to_string()))
    }

    /// Get proof size in bytes
    pub fn size(&self) -> usize {
        self.proof_bytes.len()
    }

    /// Get the raw STARK proof
    pub fn get_stark_proof(&self) -> Result<Proof, VdfError> {
        Proof::from_bytes(&self.proof_bytes)
            .map_err(|e| VdfError::SerializationError(format!("Invalid STARK proof: {:?}", e)))
    }
}

/// Configuration for VDF STARK proofs
#[derive(Clone, Debug)]
pub struct VdfProofConfig {
    /// Number of hash iterations (T)
    pub iterations: u64,

    /// How often to save checkpoints (every N iterations)
    pub checkpoint_interval: u64,

    /// Target security level in bits
    pub security_bits: u8,

    /// Number of FRI queries
    pub num_queries: usize,

    /// Blowup factor for Reed-Solomon encoding
    pub blowup_factor: usize,

    /// FRI folding factor
    pub fri_folding_factor: usize,

    /// FRI max remainder size
    pub fri_max_remainder_size: usize,
}

impl Default for VdfProofConfig {
    fn default() -> Self {
        Self {
            iterations: 16_777_216, // 2^24
            checkpoint_interval: 1000,
            security_bits: 128,
            num_queries: 30,
            blowup_factor: 8,
            fri_folding_factor: 4,
            fri_max_remainder_size: 255,  // Must be 2^n - 1
        }
    }
}

impl VdfProofConfig {
    /// Create config for Montana's default VDF parameters
    pub fn montana_default() -> Self {
        Self::default()
    }

    /// Expected number of checkpoints
    pub fn num_checkpoints(&self) -> usize {
        (self.iterations / self.checkpoint_interval) as usize
    }

    /// Validate configuration
    pub fn validate(&self) -> Result<(), VdfError> {
        if self.iterations == 0 {
            return Err(VdfError::InvalidInput("iterations must be > 0".into()));
        }
        if self.checkpoint_interval == 0 {
            return Err(VdfError::InvalidInput("checkpoint_interval must be > 0".into()));
        }
        if self.checkpoint_interval > self.iterations {
            return Err(VdfError::InvalidInput(
                "checkpoint_interval must be <= iterations".into()
            ));
        }
        if self.security_bits < 80 {
            return Err(VdfError::InvalidInput(
                "security_bits must be >= 80".into()
            ));
        }
        Ok(())
    }
}
