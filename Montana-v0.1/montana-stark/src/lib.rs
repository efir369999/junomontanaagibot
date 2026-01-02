//! Montana STARK - VDF Proof Generation and Verification
//!
//! This crate provides STARK proofs for Montana's hash-chain VDF.
//! The VDF computes: output = H^T(input) where H = SHAKE256
//!
//! STARK proves that the computation was done correctly without
//! requiring the verifier to recompute all T iterations.

pub mod vdf_air;
pub mod prover;
pub mod verifier;
pub mod types;

use pyo3::prelude::*;
use pyo3::types::PyBytes;

pub use types::{VdfProof, VdfError, VdfProofConfig};
pub use vdf_air::{VdfAir, VdfPublicInputs, TRACE_WIDTH};
pub use prover::generate_proof;
pub use verifier::verify_proof;

// Re-export field type
pub use winter_math::fields::f128::BaseElement as Felt;

/// Montana STARK Python module
#[pymodule]
fn montana_stark(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_generate_proof, m)?)?;
    m.add_function(wrap_pyfunction!(py_verify_proof, m)?)?;
    m.add_function(wrap_pyfunction!(py_get_proof_size, m)?)?;
    m.add_function(wrap_pyfunction!(py_stark_available, m)?)?;
    m.add_class::<PyVdfProof>()?;
    Ok(())
}

/// Check if STARK is available
#[pyfunction]
fn py_stark_available() -> bool {
    true
}

/// Python wrapper for VDF proof
#[pyclass]
#[derive(Clone)]
pub struct PyVdfProof {
    inner: VdfProof,
}

#[pymethods]
impl PyVdfProof {
    /// Serialize proof to bytes
    fn to_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = self.inner.to_bytes()
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        Ok(PyBytes::new_bound(py, &bytes))
    }

    /// Deserialize proof from bytes
    #[staticmethod]
    fn from_bytes(data: &[u8]) -> PyResult<Self> {
        let inner = VdfProof::from_bytes(data)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    /// Get proof size in bytes
    fn size(&self) -> usize {
        self.inner.size()
    }

    /// Get number of iterations
    fn iterations(&self) -> u64 {
        self.inner.iterations
    }
}

/// Generate STARK proof for VDF computation
#[pyfunction]
fn py_generate_proof(
    py: Python<'_>,
    input_hash: &[u8],
    output_hash: &[u8],
    checkpoints: Vec<Vec<u8>>,
    iterations: u64,
) -> PyResult<PyVdfProof> {
    // Validate inputs
    if input_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "input_hash must be 32 bytes"
        ));
    }
    if output_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "output_hash must be 32 bytes"
        ));
    }

    let input: [u8; 32] = input_hash.try_into()
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("input_hash must be 32 bytes"))?;
    let output: [u8; 32] = output_hash.try_into()
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("output_hash must be 32 bytes"))?;

    let checkpoints: Result<Vec<[u8; 32]>, _> = checkpoints
        .iter()
        .map(|cp| cp.as_slice().try_into())
        .collect();
    let checkpoints = checkpoints
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("each checkpoint must be 32 bytes"))?;

    // Generate proof (allow threads for parallelism)
    py.allow_threads(|| {
        let proof = prover::generate_proof(input, output, &checkpoints, iterations)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(PyVdfProof { inner: proof })
    })
}

/// Verify STARK proof for VDF computation
#[pyfunction]
fn py_verify_proof(
    py: Python<'_>,
    input_hash: &[u8],
    output_hash: &[u8],
    proof: &PyVdfProof,
    iterations: u64,
) -> PyResult<bool> {
    if input_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "input_hash must be 32 bytes"
        ));
    }
    if output_hash.len() != 32 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "output_hash must be 32 bytes"
        ));
    }

    let input: [u8; 32] = input_hash.try_into()
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("input_hash must be 32 bytes"))?;
    let output: [u8; 32] = output_hash.try_into()
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("output_hash must be 32 bytes"))?;

    py.allow_threads(|| {
        verify_proof(input, output, &proof.inner, iterations)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    })
}

/// Get expected proof size for given parameters
#[pyfunction]
fn py_get_proof_size(iterations: u64, checkpoint_interval: u64) -> usize {
    let num_checkpoints = (iterations / checkpoint_interval) as usize;
    let trace_len = (num_checkpoints + 2).next_power_of_two();

    // Estimate based on winterfell proof structure
    // Base: ~1KB for commitments and metadata
    // FRI: ~log2(trace_len) layers, each ~2KB
    // Queries: 27 queries * ~100 bytes each
    let fri_layers = (trace_len as f64).log2().ceil() as usize;
    1024 + fri_layers * 2048 + 27 * 100
}
