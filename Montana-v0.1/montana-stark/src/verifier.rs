//! VDF STARK Verifier
//!
//! Verifies STARK proofs for VDF hash chain computations.
//! Verification is O(log T) compared to O(T) for recomputation.

use crate::types::{VdfError, VdfProof};
use crate::vdf_air::{Felt, VdfAir, VdfPublicInputs};

use winter_air::{FieldExtension, ProofOptions};
use winter_crypto::{hashers::Blake3_256, DefaultRandomCoin};
use winterfell::AcceptableOptions;

// Type aliases for STARK components (must match prover)
type VdfHasher = Blake3_256<Felt>;
type VdfRandomCoin = DefaultRandomCoin<VdfHasher>;

/// Verify STARK proof for VDF computation
///
/// # Arguments
/// * `input` - 32-byte input to VDF
/// * `output` - 32-byte expected output
/// * `proof` - The VDF STARK proof to verify
/// * `iterations` - Total number of iterations (T)
///
/// # Returns
/// * `Ok(true)` if proof is valid
/// * `Ok(false)` if proof is invalid
/// * `Err` if verification encounters an error
pub fn verify_proof(
    input: [u8; 32],
    output: [u8; 32],
    proof: &VdfProof,
    iterations: u64,
) -> Result<bool, VdfError> {
    // Validate iterations match
    if proof.iterations != iterations {
        return Err(VdfError::InvalidInput(format!(
            "Proof iterations {} don't match expected {}",
            proof.iterations, iterations
        )));
    }

    // Create public inputs
    let pub_inputs = VdfPublicInputs::new(input, output, iterations);

    // Get the STARK proof
    let stark_proof = proof.get_stark_proof()?;

    // Create acceptable options for verification
    let acceptable_options = AcceptableOptions::OptionSet(vec![
        ProofOptions::new(
            30,  // num_queries
            8,   // blowup_factor
            0,   // grinding factor
            FieldExtension::None,
            4,   // fri_folding_factor
            255, // fri_max_remainder_size (must be 2^n - 1)
        ),
    ]);

    // Verify using winterfell
    match winterfell::verify::<VdfAir, VdfHasher, VdfRandomCoin>(stark_proof, pub_inputs, &acceptable_options) {
        Ok(_) => Ok(true),
        Err(e) => {
            // Log verification failure reason
            eprintln!("STARK verification failed: {:?}", e);
            Ok(false)
        }
    }
}

/// Verify proof with custom options
pub fn verify_proof_with_options(
    input: [u8; 32],
    output: [u8; 32],
    proof: &VdfProof,
    iterations: u64,
    num_queries: usize,
    blowup_factor: usize,
) -> Result<bool, VdfError> {
    if proof.iterations != iterations {
        return Err(VdfError::InvalidInput(format!(
            "Proof iterations {} don't match expected {}",
            proof.iterations, iterations
        )));
    }

    let pub_inputs = VdfPublicInputs::new(input, output, iterations);
    let stark_proof = proof.get_stark_proof()?;

    let acceptable_options = AcceptableOptions::OptionSet(vec![
        ProofOptions::new(
            num_queries,
            blowup_factor,
            0,
            FieldExtension::None,
            4,   // fri_folding_factor
            255, // fri_max_remainder_size (must be 2^n - 1)
        ),
    ]);

    match winterfell::verify::<VdfAir, VdfHasher, VdfRandomCoin>(stark_proof, pub_inputs, &acceptable_options) {
        Ok(_) => Ok(true),
        Err(_) => Ok(false),
    }
}

/// Quick check if proof structure is valid (without full verification)
pub fn validate_proof_structure(proof: &VdfProof) -> Result<(), VdfError> {
    // Check proof can be deserialized
    let _ = proof.get_stark_proof()?;

    // Check reasonable sizes
    if proof.iterations == 0 {
        return Err(VdfError::InvalidInput("iterations cannot be 0".into()));
    }

    if proof.checkpoint_interval == 0 {
        return Err(VdfError::InvalidInput("checkpoint_interval cannot be 0".into()));
    }

    if proof.security_bits < 80 {
        return Err(VdfError::InvalidInput("security_bits must be >= 80".into()));
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_proof_structure() {
        // This would require a valid proof to test properly
        // For now, just ensure the function compiles
    }
}
