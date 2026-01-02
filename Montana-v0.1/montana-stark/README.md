# Montana STARK

STARK proofs for Montana VDF verification.

## Overview

This crate provides STARK (Scalable Transparent ARgument of Knowledge) proofs for verifying Montana's hash-chain VDF computations. Instead of re-computing all T iterations to verify, a verifier can check a STARK proof in O(log T) time.

## Building

### Prerequisites

- Rust 1.70+
- Python 3.9+ (for bindings)
- maturin (for building Python package)

### Build Rust library

```bash
cargo build --release
```

### Build Python package

```bash
pip install maturin
maturin develop --release
```

## Usage

### Python

```python
from montana_stark import generate_proof, verify_proof, PyVdfProof

# After computing VDF with checkpoints
input_hash = bytes(32)  # Your input
output_hash = vdf_output  # Result of H^T(input)
checkpoints = [...]  # List of intermediate hashes

# Generate proof
proof = generate_proof(input_hash, output_hash, checkpoints, iterations=16777216)

# Verify proof (fast - O(log T))
is_valid = verify_proof(input_hash, output_hash, proof, iterations=16777216)

# Serialize/deserialize
proof_bytes = proof.to_bytes()
proof = PyVdfProof.from_bytes(proof_bytes)
```

### Rust

```rust
use montana_stark::{generate_proof, verify_proof};

let input = [0u8; 32];
let output = compute_vdf(&input, iterations);
let checkpoints = get_checkpoints();

// Generate proof
let proof = generate_proof(input, output, &checkpoints, iterations)?;

// Verify
let valid = verify_proof(input, output, &proof, iterations)?;
```

## Architecture

```
montana-stark/
├── Cargo.toml          # Dependencies and build config
├── README.md           # This file
├── src/
│   ├── lib.rs          # PyO3 bindings, module entry point
│   ├── types.rs        # VdfProof, VdfError, VdfProofConfig
│   ├── vdf_air.rs      # AIR constraint system (Algebraic IR)
│   ├── prover.rs       # STARK proof generation
│   └── verifier.rs     # STARK proof verification
├── tests/
│   └── integration_tests.rs  # End-to-end tests
└── benches/
    └── vdf_stark.rs    # Performance benchmarks
```

## How It Works

1. **VDF Computation**: `output = H^T(input)` where H = SHAKE256, T = 2^24
2. **Checkpoints**: Save hash state every N iterations during computation
3. **AIR**: Encode "next_state = H(current_state)" as algebraic constraints
4. **STARK Proof**: Prove all constraints satisfied using FRI protocol
5. **Verification**: Check proof in O(log T) without re-computing

## Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Hash function | SHAKE256 | Post-quantum secure |
| Iterations (T) | 2^24 | ~2.5 seconds |
| Checkpoint interval | 1000 | Balance: proof size vs prover time |
| Security level | 128 bits | |
| FRI queries | 30 | |
| Blowup factor | 8 | Reed-Solomon expansion |

## Performance Targets

| Operation | Time | Notes |
|-----------|------|-------|
| VDF compute | ~2.5s | Sequential, cannot parallelize |
| Proof generate | ~5-10s | Parallelizable |
| Proof verify | ~50ms | O(log T) |
| Proof size | ~50-100 KB | Depends on parameters |

## Dependencies

- [winterfell](https://github.com/facebook/winterfell) - STARK prover/verifier
- [sha3](https://crates.io/crates/sha3) - SHAKE256 implementation
- [pyo3](https://pyo3.rs/) - Python bindings

## Status

**Implementation Status**: Core framework complete.

**Completed**:
- STARK proof generation using winterfell 0.9
- STARK proof verification (O(log T))
- Python bindings via PyO3
- Proof serialization/deserialization
- Integration tests
- Benchmark framework

**Pending**:
- Full SHAKE256 AIR constraints (current: placeholder constraints)
- Performance benchmarks with production parameters
- External security audit

## License

MIT
