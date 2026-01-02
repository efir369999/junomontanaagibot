//! Benchmarks for Montana STARK VDF proofs
//!
//! Run with: cargo bench

use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use sha3::{Shake256, digest::{Update, ExtendableOutput, XofReader}};

/// Compute VDF (SHAKE256 hash chain) for benchmarking
fn compute_vdf(input: &[u8; 32], iterations: u64) -> ([u8; 32], Vec<[u8; 32]>) {
    let checkpoint_interval = 1000u64;
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

fn benchmark_vdf_computation(c: &mut Criterion) {
    let input = [0u8; 32];

    let mut group = c.benchmark_group("VDF Computation");

    // Benchmark different iteration counts
    for iterations in [1_000u64, 10_000, 100_000].iter() {
        group.bench_with_input(
            BenchmarkId::from_parameter(iterations),
            iterations,
            |b, &iters| {
                b.iter(|| compute_vdf(black_box(&input), black_box(iters)));
            },
        );
    }

    group.finish();
}

fn benchmark_single_hash(c: &mut Criterion) {
    let input = [0u8; 32];

    c.bench_function("single SHAKE256", |b| {
        b.iter(|| {
            let mut hasher = Shake256::default();
            hasher.update(black_box(&input));
            let mut reader = hasher.finalize_xof();
            let mut output = [0u8; 32];
            reader.read(&mut output);
            output
        });
    });
}

// Note: STARK proof benchmarks would require the full library to be built
// These are commented out until the library compiles successfully

/*
fn benchmark_stark_proof_generation(c: &mut Criterion) {
    use montana_stark::{generate_proof, VdfProofConfig};

    let input = [0u8; 32];
    let iterations = 10_000u64;
    let (output, checkpoints) = compute_vdf(&input, iterations);

    c.bench_function("STARK proof generation (10k iterations)", |b| {
        b.iter(|| {
            generate_proof(
                black_box(input),
                black_box(output),
                black_box(&checkpoints),
                black_box(iterations),
            )
        });
    });
}

fn benchmark_stark_verification(c: &mut Criterion) {
    use montana_stark::{generate_proof, verify_proof};

    let input = [0u8; 32];
    let iterations = 10_000u64;
    let (output, checkpoints) = compute_vdf(&input, iterations);

    // Pre-generate proof
    let proof = generate_proof(input, output, &checkpoints, iterations).unwrap();

    c.bench_function("STARK proof verification (10k iterations)", |b| {
        b.iter(|| {
            verify_proof(
                black_box(input),
                black_box(output),
                black_box(&proof),
                black_box(iterations),
            )
        });
    });
}
*/

criterion_group!(benches, benchmark_vdf_computation, benchmark_single_hash);
criterion_main!(benches);
