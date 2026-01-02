//! VDF STARK Prover
//!
//! Generates STARK proofs for VDF hash chain computations.

use crate::types::{VdfError, VdfProof, VdfProofConfig};
use crate::vdf_air::{Felt, VdfAir, VdfPublicInputs, TRACE_WIDTH};

use sha3::{Shake256, digest::{Update, ExtendableOutput, XofReader}};
use winter_air::{FieldExtension, ProofOptions};
use winter_crypto::{hashers::Blake3_256, DefaultRandomCoin};
use winter_math::FieldElement;
use winterfell::TraceTable;

// Type aliases for STARK components
type VdfHasher = Blake3_256<Felt>;
type VdfRandomCoin = DefaultRandomCoin<VdfHasher>;

/// Generate STARK proof for VDF computation
///
/// # Arguments
/// * `input` - 32-byte input to VDF
/// * `output` - 32-byte expected output
/// * `checkpoints` - Intermediate hash values at checkpoint intervals
/// * `iterations` - Total number of iterations (T)
///
/// # Returns
/// * `VdfProof` containing the STARK proof
pub fn generate_proof(
    input: [u8; 32],
    output: [u8; 32],
    checkpoints: &[[u8; 32]],
    iterations: u64,
) -> Result<VdfProof, VdfError> {
    let config = VdfProofConfig::montana_default();
    generate_proof_with_config(input, output, checkpoints, iterations, config)
}

/// Generate STARK proof with custom configuration
pub fn generate_proof_with_config(
    input: [u8; 32],
    output: [u8; 32],
    checkpoints: &[[u8; 32]],
    iterations: u64,
    config: VdfProofConfig,
) -> Result<VdfProof, VdfError> {
    // Validate inputs
    config.validate()?;

    let expected_checkpoints = config.num_checkpoints();
    if checkpoints.len() != expected_checkpoints {
        return Err(VdfError::InvalidCheckpointCount {
            expected: expected_checkpoints,
            got: checkpoints.len(),
        });
    }

    // Verify the VDF computation is correct before generating proof
    verify_vdf_computation(&input, &output, checkpoints, iterations, config.checkpoint_interval)?;

    // Build execution trace from checkpoints
    let trace = build_trace(&input, checkpoints, &output)?;

    // Create proof options
    // winterfell 0.9: new(num_queries, blowup_factor, grinding_factor, field_extension)
    let options = ProofOptions::new(
        config.num_queries,
        config.blowup_factor,
        0,  // grinding factor
        FieldExtension::None,  // No field extension needed for 128-bit security
    );

    // Create public inputs
    let pub_inputs = VdfPublicInputs::new(input, output, iterations);

    // Generate the STARK proof using winterfell
    let stark_proof = winterfell::prove::<VdfAir, VdfHasher, VdfRandomCoin>(
        trace,
        pub_inputs,
        options,
    ).map_err(|e| VdfError::ProofGenerationFailed(format!("{:?}", e)))?;

    // Package into VdfProof
    VdfProof::from_stark_proof(
        stark_proof,
        iterations,
        config.checkpoint_interval,
        config.security_bits,
    )
}

/// Verify VDF computation is correct before generating proof
fn verify_vdf_computation(
    input: &[u8; 32],
    expected_output: &[u8; 32],
    checkpoints: &[[u8; 32]],
    iterations: u64,
    checkpoint_interval: u64,
) -> Result<(), VdfError> {
    let mut state = *input;
    let mut checkpoint_idx = 0;

    for i in 0..iterations {
        // Hash step
        state = shake256_hash(&state);

        // Check against checkpoint
        if (i + 1) % checkpoint_interval == 0 && checkpoint_idx < checkpoints.len() {
            if state != checkpoints[checkpoint_idx] {
                return Err(VdfError::InvalidInput(format!(
                    "Checkpoint {} mismatch at iteration {}",
                    checkpoint_idx,
                    i + 1
                )));
            }
            checkpoint_idx += 1;
        }
    }

    if state != *expected_output {
        return Err(VdfError::InvalidInput(
            "Output hash does not match VDF computation".into()
        ));
    }

    Ok(())
}

/// Compute SHAKE256 hash
fn shake256_hash(input: &[u8; 32]) -> [u8; 32] {
    let mut hasher = Shake256::default();
    hasher.update(input);
    let mut reader = hasher.finalize_xof();
    let mut output = [0u8; 32];
    reader.read(&mut output);
    output
}

/// Build execution trace from checkpoints
fn build_trace(
    input: &[u8; 32],
    checkpoints: &[[u8; 32]],
    output: &[u8; 32],
) -> Result<TraceTable<Felt>, VdfError> {
    // Trace length = input + checkpoints + output
    let trace_len = checkpoints.len() + 2;

    // Ensure power of 2 for FFT
    let trace_len = trace_len.next_power_of_two();

    // Initialize trace columns
    let mut columns: Vec<Vec<Felt>> = vec![vec![Felt::ZERO; trace_len]; TRACE_WIDTH];

    // Fill first row with input
    let input_felts = bytes_to_felts(input);
    for (col, &value) in input_felts.iter().enumerate() {
        columns[col][0] = value;
    }

    // Fill checkpoint rows
    for (i, checkpoint) in checkpoints.iter().enumerate() {
        let felts = bytes_to_felts(checkpoint);
        for (col, &value) in felts.iter().enumerate() {
            columns[col][i + 1] = value;
        }
    }

    // Fill last meaningful row with output
    let output_felts = bytes_to_felts(output);
    let output_row = checkpoints.len() + 1;
    for (col, &value) in output_felts.iter().enumerate() {
        columns[col][output_row] = value;
    }

    // Pad remaining rows (if any) with output value
    for row in (output_row + 1)..trace_len {
        for (col, &value) in output_felts.iter().enumerate() {
            columns[col][row] = value;
        }
    }

    // Create TraceTable from columns
    Ok(TraceTable::init(columns))
}

/// Convert 32-byte hash to field elements
fn bytes_to_felts(bytes: &[u8; 32]) -> [Felt; TRACE_WIDTH] {
    let mut result = [Felt::ZERO; TRACE_WIDTH];
    for i in 0..TRACE_WIDTH {
        let start = i * 8;
        let chunk: [u8; 8] = bytes[start..start + 8].try_into().unwrap();
        result[i] = Felt::from(u64::from_le_bytes(chunk));
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shake256_hash() {
        let input = [0u8; 32];
        let output = shake256_hash(&input);
        assert_ne!(input, output);
    }

    #[test]
    fn test_bytes_felts_roundtrip() {
        let original = [1u8; 32];
        let felts = bytes_to_felts(&original);

        let mut recovered = [0u8; 32];
        for i in 0..TRACE_WIDTH {
            let value = felts[i].as_int() as u64;
            recovered[i * 8..(i + 1) * 8].copy_from_slice(&value.to_le_bytes());
        }

        assert_eq!(original, recovered);
    }
}
