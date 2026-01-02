#!/usr/bin/env python3
"""
Montana VDF Benchmark

Measures SHAKE256 hash chain performance for VDF timing analysis.
Results are used to validate whitepaper claims.
"""

import time
import hashlib
import statistics
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class BenchmarkResult:
    iterations: int
    total_time_sec: float
    time_per_iteration_ns: float
    iterations_per_sec: float


def shake256_32(data: bytes) -> bytes:
    """Single SHAKE256 iteration producing 32 bytes."""
    return hashlib.shake_256(data).digest(32)


def compute_vdf(input_data: bytes, iterations: int) -> Tuple[bytes, float]:
    """
    Compute VDF: output = H^T(input) where H = SHAKE256.

    Returns (output, elapsed_seconds).
    """
    state = input_data
    start = time.perf_counter()

    for _ in range(iterations):
        state = shake256_32(state)

    elapsed = time.perf_counter() - start
    return state, elapsed


def benchmark_single_hash(runs: int = 10000) -> float:
    """Benchmark single SHAKE256 operation."""
    data = b'\x00' * 32

    start = time.perf_counter()
    for _ in range(runs):
        data = shake256_32(data)
    elapsed = time.perf_counter() - start

    return (elapsed / runs) * 1e9  # nanoseconds


def benchmark_vdf(iterations: int, runs: int = 3) -> BenchmarkResult:
    """Benchmark VDF computation."""
    times = []
    input_data = b'\x00' * 32

    for _ in range(runs):
        _, elapsed = compute_vdf(input_data, iterations)
        times.append(elapsed)

    avg_time = statistics.mean(times)

    return BenchmarkResult(
        iterations=iterations,
        total_time_sec=avg_time,
        time_per_iteration_ns=(avg_time / iterations) * 1e9,
        iterations_per_sec=iterations / avg_time,
    )


def main():
    print("=" * 60)
    print("Montana VDF Benchmark")
    print("=" * 60)

    # System info
    import platform
    print(f"\nPlatform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Processor: {platform.processor() or 'N/A'}")

    # Single hash benchmark
    print("\n" + "-" * 60)
    print("Single SHAKE256 (32-byte output)")
    print("-" * 60)

    ns_per_hash = benchmark_single_hash(100000)
    print(f"Time per hash: {ns_per_hash:.1f} ns")
    print(f"Hashes per second: {1e9/ns_per_hash:,.0f}")

    # VDF benchmarks at various iteration counts
    print("\n" + "-" * 60)
    print("VDF Hash Chain Benchmark")
    print("-" * 60)

    test_iterations = [
        1_000,
        10_000,
        100_000,
        1_000_000,
        10_000_000,
    ]

    results = []
    for iters in test_iterations:
        print(f"\nBenchmarking {iters:,} iterations...", end=" ", flush=True)
        result = benchmark_vdf(iters, runs=3)
        results.append(result)
        print(f"{result.total_time_sec:.3f}s")

    # Results table
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    print(f"{'Iterations':<15} {'Time (sec)':<12} {'ns/iter':<12} {'iter/sec':<15}")
    print("-" * 60)

    for r in results:
        print(f"{r.iterations:<15,} {r.total_time_sec:<12.4f} {r.time_per_iteration_ns:<12.1f} {r.iterations_per_sec:<15,.0f}")

    # Extrapolate to 2^24
    print("\n" + "-" * 60)
    print("Extrapolation to Montana VDF Parameters")
    print("-" * 60)

    # Use the most accurate measurement (longest run)
    best_result = results[-1]
    ns_per_iter = best_result.time_per_iteration_ns

    vdf_iterations = 2**24  # 16,777,216
    estimated_time = (vdf_iterations * ns_per_iter) / 1e9

    print(f"\nVDF_BASE_ITERATIONS = 2^24 = {vdf_iterations:,}")
    print(f"Estimated time per VDF checkpoint: {estimated_time:.2f} seconds")
    print(f"Time per iteration: {ns_per_iter:.1f} ns")

    # Finality estimates
    print("\n" + "-" * 60)
    print("Finality Timing Estimates")
    print("-" * 60)
    print(f"Soft finality (1 checkpoint):    {estimated_time:.1f} seconds")
    print(f"Medium finality (100 checkpoints): {estimated_time * 100 / 60:.1f} minutes")
    print(f"Hard finality (1000 checkpoints):  {estimated_time * 1000 / 60:.1f} minutes")

    # ASIC considerations
    print("\n" + "-" * 60)
    print("ASIC Speedup Analysis")
    print("-" * 60)
    print(f"Current: {ns_per_iter:.1f} ns/iteration (software, {platform.processor() or 'CPU'})")
    print(f"ASIC estimate: ~20-50 ns/iteration (Keccak ASIC)")
    print(f"ASIC speedup factor: ~{ns_per_iter/35:.1f}x")
    print(f"ASIC VDF time: ~{(vdf_iterations * 35) / 1e9:.2f} seconds")

    # Security margin
    print("\n" + "-" * 60)
    print("Security Margin")
    print("-" * 60)
    asic_time = (vdf_iterations * 35) / 1e9  # 35ns estimate for ASIC
    print(f"Whitepaper claims: ~2.5 seconds per checkpoint")
    print(f"This benchmark: {estimated_time:.2f} seconds (software)")
    print(f"ASIC estimate: {asic_time:.2f} seconds")
    print(f"Security margin vs ASIC: {estimated_time/asic_time:.1f}x")

    # Run actual 2^24 if time permits (optional)
    print("\n" + "-" * 60)
    print("Full VDF Computation (2^24 iterations)")
    print("-" * 60)

    if estimated_time < 30:  # Only run if estimated < 30 seconds
        print(f"Running 2^24 = {vdf_iterations:,} iterations...")
        result = benchmark_vdf(vdf_iterations, runs=1)
        print(f"Actual time: {result.total_time_sec:.3f} seconds")
        print(f"Actual ns/iter: {result.time_per_iteration_ns:.1f}")
    else:
        print(f"Skipping (estimated time {estimated_time:.1f}s > 30s threshold)")

    print("\n" + "=" * 60)
    print("Benchmark Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
