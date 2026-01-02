# Montana v3.1: Quick Reference

**Status:** Specification complete, implementation partial
**Type:** Layer 3+ Implementation (Temporal Consensus Protocol)
**ATC Compatibility:** v10.0

---

## One-Line Summary

Montana is a temporal consensus protocol for asymptotic trust in time value, grounding security in physics.

---

## Implementation Status

| Component | Status |
|-----------|--------|
| Core protocol | ✅ Implemented |
| VDF (hash chain) | ✅ Implemented |
| STARK proofs | ❌ Specification only |
| Privacy T1-T3 | ⚠ Partial |
| NTP servers | ⚠ List unverified |

---

## Design Checklist

| Question | Answer |
|----------|--------|
| Violates physics? | No — respects L-1 |
| Uses broken crypto? | No — NIST PQC standards |
| Claims too strong? | No — correctly typed |
| Has upgrade paths? | Yes — for all PQ-vulnerable |
| Fair launch? | Yes — zero pre-allocation |
| Externally audited? | **No — pending** |

---

## ATC Layer Compliance (Design Goal)

```
L-1 Physical:    ✓ Atomic time, Landauer, light speed
L0 Computation:  ✓ SHA-3, SPHINCS+, ML-KEM
L1 Primitives:   ✓ VDF*, VRF**, Commitment, Timestamp
L2 Consensus:    ✓ DAG, BFT, Finality

*  VDF uses hash chain (empirical sequentiality)
** ECVRF quantum-vulnerable — documented, upgrade path exists
```

---

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Total Supply | 1,260,000,000 Ɉ |
| Time Unit | 1 Ɉ → 1 second (asymptotic) |
| Block Reward | 3,000 Ɉ (halving) |
| Block Time | ~10 minutes |
| NTP Sources | 34 (8 regions) — unverified |
| BFT Threshold | f < n/3 |
| Finality | Accumulated VDF |

---

## Quantum Status

| ✅ PQ-Secure | ⚠ PQ-Vulnerable (Documented) |
|--------------|------------------------------|
| SPHINCS+ | ECVRF (short-term) |
| ML-KEM | Pedersen binding |
| SHA-3/SHAKE | Ring signatures |

---

## What Would Break It

| If This Breaks | Impact | Recovery |
|----------------|--------|----------|
| SHA-3 | Critical | Replace hash |
| SPHINCS+ | Critical | Replace sig scheme |
| MLWE | Critical | Replace KEM |
| ECVRF | Low | Lattice-VRF |
| VDF Sequentiality | High | Increase iterations |
| Physics | Total | None |

---

## Known Limitations

1. **STARK proofs** — not implemented, light clients cannot verify efficiently
2. **VDF** — hash chain (empirical), not group-based (proven)
3. **NTP list** — specified but not tested for accessibility
4. **Privacy T2/T3** — quantum-vulnerable components

---

## Quick Reference Links

| Document | Purpose |
|----------|---------|
| [WHITEPAPER.md](WHITEPAPER.md) | Conceptual overview |
| [MONTANA_TECHNICAL_SPECIFICATION.md](MONTANA_TECHNICAL_SPECIFICATION.md) | Implementation details |
| [MONTANA_ATC_MAPPING.md](MONTANA_ATC_MAPPING.md) | Layer mapping |
| [HYPERCRITICISM_PROOF.md](HYPERCRITICISM_PROOF.md) | Self-assessment |

---

*Montana v3.1 — Specification complete, audit pending.*
