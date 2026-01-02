//! Integration tests for Montana STARK VDF proofs

use montana_stark::{generate_proof, verify_proof, VdfProofConfig, VdfError};
use sha3::{Shake256, digest::{Update, ExtendableOutput, XofReader}};

/// Compute VDF and checkpoints for testing
fn compute_vdf_with_checkpoints(
    input: &[u8; 32],
    iterations: u64,
    checkpoint_interval: u64,
) -> ([u8; 32], Vec<[u8; 32]>) {
    let mut state = *input;
    let mut checkpoints = Vec::new();

    for i in 0..iterations {
        let mut hasher = Shake256::default();
        hasher.update(&state);
        let mut reader = hasher.finalize_xof();
        reader.read(&mut state);

        if (i + 1) % checkpoint_interval == 0 {
            checkpoints.push(state);
        }
    }

    (state, checkpoints)
}

#[test]
fn test_proof_generation_and_verification() {
    // Use small parameters for fast testing
    let input = [0u8; 32];
    let iterations = 4000u64;  // Small number for fast test
    let checkpoint_interval = 1000u64;

    // Compute VDF
    let (output, checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Generate proof
    let config = VdfProofConfig {
        iterations,
        checkpoint_interval,
        security_bits: 128,
        num_queries: 30,
        blowup_factor: 8,
    };

    let proof = montana_stark::prover::generate_proof_with_config(
        input,
        output,
        &checkpoints,
        iterations,
        config,
    ).expect("Proof generation should succeed");

    // Verify proof
    let is_valid = verify_proof(input, output, &proof, iterations)
        .expect("Verification should not error");

    assert!(is_valid, "Valid proof should verify successfully");
}

#[test]
fn test_proof_fails_with_wrong_output() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Tamper with output
    let mut wrong_output = output;
    wrong_output[0] ^= 0xFF;

    // Proof generation should fail because output doesn't match
    let result = generate_proof(input, wrong_output, &checkpoints, iterations);
    assert!(result.is_err(), "Proof generation should fail with wrong output");
}

#[test]
fn test_proof_fails_with_wrong_checkpoint() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, mut checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Tamper with a checkpoint
    if !checkpoints.is_empty() {
        checkpoints[0][0] ^= 0xFF;
    }

    // Proof generation should fail
    let result = generate_proof(input, output, &checkpoints, iterations);
    assert!(result.is_err(), "Proof generation should fail with wrong checkpoint");
}

#[test]
fn test_verification_fails_with_wrong_input() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Generate valid proof
    let proof = generate_proof(input, output, &checkpoints, iterations)
        .expect("Proof generation should succeed");

    // Try to verify with wrong input
    let mut wrong_input = input;
    wrong_input[0] = 0xFF;

    let is_valid = verify_proof(wrong_input, output, &proof, iterations)
        .expect("Verification should not error");

    assert!(!is_valid, "Proof should not verify with wrong input");
}

#[test]
fn test_proof_serialization() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Generate proof
    let proof = generate_proof(input, output, &checkpoints, iterations)
        .expect("Proof generation should succeed");

    // Serialize
    let bytes = proof.to_bytes().expect("Serialization should succeed");

    // Deserialize
    let recovered = montana_stark::VdfProof::from_bytes(&bytes)
        .expect("Deserialization should succeed");

    // Verify recovered proof
    let is_valid = verify_proof(input, output, &recovered, iterations)
        .expect("Verification should not error");

    assert!(is_valid, "Recovered proof should verify");
}

#[test]
fn test_checkpoint_count_validation() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, mut checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Remove a checkpoint
    checkpoints.pop();

    // Proof generation should fail due to wrong checkpoint count
    let result = generate_proof(input, output, &checkpoints, iterations);
    assert!(matches!(result, Err(VdfError::InvalidCheckpointCount { .. })));
}

#[test]
fn test_iterations_mismatch() {
    let input = [0u8; 32];
    let iterations = 4000u64;
    let checkpoint_interval = 1000u64;

    let (output, checkpoints) = compute_vdf_with_checkpoints(&input, iterations, checkpoint_interval);

    // Generate proof with correct iterations
    let proof = generate_proof(input, output, &checkpoints, iterations)
        .expect("Proof generation should succeed");

    // Try to verify with different iterations
    let result = verify_proof(input, output, &proof, iterations + 1000);
    assert!(result.is_err(), "Verification should fail with mismatched iterations");
}
