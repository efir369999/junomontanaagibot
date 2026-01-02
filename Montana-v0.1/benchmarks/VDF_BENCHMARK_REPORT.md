# Montana VDF Benchmark Report

**Date:** January 2026
**Benchmark Version:** 1.0

---

## Summary

This report documents VDF (Verifiable Delay Function) timing measurements for Montana's hash-chain construction using SHAKE256.

**Key Finding:** The whitepaper claim of "~2.5 seconds per VDF checkpoint" requires revision. Actual measurements show 10-25 seconds depending on hardware.

---

## Test Environment

### Server (Timeweb VPS)

| Parameter | Value |
|-----------|-------|
| Platform | Linux 6.8.0-62-generic x86_64 |
| CPU | QEMU Virtual CPU version 4.2.0 |
| Clock | 2100 MHz |
| Python | 3.12.3 |
| Hash Library | hashlib (OpenSSL backend) |

### Local (Apple Silicon)

| Parameter | Value |
|-----------|-------|
| Platform | macOS 15.7.2 arm64 |
| CPU | Apple M3 |
| Python | 3.12.2 |
| Hash Library | hashlib (OpenSSL backend) |

---

## Results

### Single SHAKE256 Operation

| Platform | Time per hash | Hashes/sec |
|----------|---------------|------------|
| Timeweb VPS | 1,599 ns | 625,431 |
| Apple M3 | 678 ns | 1,475,834 |

### VDF Hash Chain (H^T iterations)

#### Timeweb VPS Results

| Iterations | Time (sec) | ns/iter | iter/sec |
|------------|------------|---------|----------|
| 1,000 | 0.002 | 1,897 | 527,119 |
| 10,000 | 0.021 | 2,123 | 471,000 |
| 100,000 | 0.193 | 1,932 | 517,666 |
| 1,000,000 | 1.271 | 1,271 | 786,922 |
| 10,000,000 | 13.986 | 1,399 | 715,002 |
| **16,777,216 (2^24)** | **23.096** | **1,377** | **726,449** |

#### Apple M3 Results

| Iterations | Time (sec) | ns/iter | iter/sec |
|------------|------------|---------|----------|
| 1,000 | 0.001 | 640 | 1,562,906 |
| 10,000 | 0.007 | 663 | 1,508,966 |
| 100,000 | 0.069 | 694 | 1,441,642 |
| 1,000,000 | 0.664 | 664 | 1,505,288 |
| 10,000,000 | 6.545 | 655 | 1,527,816 |
| **16,777,216 (2^24)** | **~11** | **~655** | **~1,527,000** |

---

## Analysis

### Whitepaper Discrepancy

| Metric | Whitepaper | Timeweb VPS | Apple M3 |
|--------|------------|-------------|----------|
| VDF checkpoint time | ~2.5 sec | **23.1 sec** | **~11 sec** |
| Required ns/iter | 149 ns | 1,377 ns | 655 ns |

The whitepaper claim of 2.5 seconds requires ~149 ns/iteration, which is achievable only with:
- High-frequency native CPU (4+ GHz, not virtualized)
- Keccak/SHA-3 hardware acceleration
- Dedicated ASIC

### Iterations Required for 2.5 Second Target

| Hardware | ns/iter | Iterations for 2.5s |
|----------|---------|---------------------|
| Timeweb VPS | 1,377 | 1,815,541 (~2^21) |
| Apple M3 | 655 | 3,816,793 (~2^22) |
| Fast x86_64 (4GHz+) | ~300 | 8,333,333 (~2^23) |
| Keccak ASIC | ~35 | 71,428,571 (~2^26) |

### ASIC Considerations

Keccak (SHA-3/SHAKE256) ASICs exist with ~20-50 ns per operation. For security analysis:

| Scenario | Time for 2^24 iterations |
|----------|--------------------------|
| Software (slow) | 23 seconds |
| Software (fast) | 11 seconds |
| ASIC (35 ns/iter) | **0.59 seconds** |

**Security implication:** An attacker with ASIC can compute VDF ~40x faster than software on commodity hardware.

---

## Recommendations

### Option 1: Update Whitepaper (Recommended)

Keep VDF_BASE_ITERATIONS = 2^24, update documentation:

```
VDF checkpoint time: ~10-25 seconds (software)
                     ~0.5-1 second (ASIC)

Finality levels:
- Soft (1 checkpoint): 10-25 seconds
- Medium (100 checkpoints): ~20-40 minutes
- Hard (1000 checkpoints): ~3-7 hours
```

**Rationale:** ASIC is the security-relevant reference. Software timing is implementation detail.

### Option 2: Reduce Iterations

Change VDF_BASE_ITERATIONS = 2^21 for ~2.5 seconds on mid-range hardware.

**Downside:** Reduces ASIC attack cost to ~70ms per checkpoint.

### Option 3: Parameterize by Hardware Class

Define multiple VDF profiles:

```python
VDF_PROFILES = {
    "consumer": 2**21,    # ~2.5s on mid-range CPU
    "server": 2**24,      # ~10-25s on server CPU
    "asic_resistant": 2**28,  # ~10s even with ASIC
}
```

---

## Finality Timing (Revised Estimates)

Using 2^24 iterations:

| Finality Level | Checkpoints | Time (Software) | Time (ASIC) |
|----------------|-------------|-----------------|-------------|
| Soft | 1 | 10-25 sec | ~0.6 sec |
| Medium | 100 | 17-42 min | ~1 min |
| Hard | 1000 | 2.8-7 hours | ~10 min |

**Security note:** Attack cost is measured in ASIC time. An attacker with ASIC hardware needs ~10 minutes to rewrite 1000 checkpoints (hard finality). This is the relevant security bound.

---

## Benchmark Code

Location: `Montana-v0.1/benchmarks/vdf_benchmark.py`

```bash
# Run benchmark
python3 benchmarks/vdf_benchmark.py
```

---

## Conclusion

1. The whitepaper claim of "~2.5 seconds" is **incorrect** for 2^24 iterations on commodity hardware.

2. Actual software timing is **10-25 seconds** depending on CPU.

3. ASIC timing is **~0.6 seconds** — this is the security-relevant bound.

4. Recommendation: Update whitepaper to reflect ASIC as the security reference, with software timing as implementation guidance.

---

**Benchmark conducted:** January 2, 2026
**Hardware:** Timeweb VPS (QEMU 2.1GHz), Apple M3
