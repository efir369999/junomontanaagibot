# Layer 3+ Montana: Design Self-Assessment

**Document Version:** 2.0
**Date:** January 2026
**Type:** Self-Assessment (NOT independent audit)

---

## Document Purpose

This document is a **self-assessment** of Montana's design against ATC layer requirements. It is NOT an independent certification. An external audit is required before production deployment.

---

## Implementation Status

| Component | Specification | Implementation | Notes |
|-----------|---------------|----------------|-------|
| VDF (hash chain) | ✅ Complete | ✅ Complete | SHAKE256 iteration |
| STARK proofs | ✅ Specified | ❌ Not implemented | O(log T) verification target |
| NTP consensus | ✅ Specified | ⚠ Partial | Server list needs verification |
| Privacy T0 | ✅ Complete | ✅ Complete | Transparent |
| Privacy T1-T3 | ✅ Specified | ⚠ Partial | Stealth/Pedersen/Ring |
| Network protocol | ✅ Complete | ✅ Complete | P2P messaging |
| Consensus | ✅ Complete | ✅ Complete | DAG + deepest chain |

---

## Design Goals (Self-Assessment)

### ATC Layer Compliance

| Layer | Requirement | Status | Notes |
|-------|-------------|--------|-------|
| L-1 | Physical constraints only | ✅ Goal met | Atomic time, VDF sequentiality |
| L0 | Standard cryptography | ✅ Goal met | NIST FIPS 202/203/205 |
| L1 | Correct primitive usage | ✅ Goal met | VDF, VRF, Commitment |
| L2 | Consensus properties | ✅ Goal met | Safety, Liveness, Finality |

### Quantum Status

| Component | Status | Documented | Upgrade Path |
|-----------|--------|------------|--------------|
| SPHINCS+ | PQ-secure | ✅ | — |
| ML-KEM | PQ-secure | ✅ | — |
| SHA-3/SHAKE | PQ-secure | ✅ | — |
| ECVRF | PQ-broken | ✅ | Lattice-VRF |
| Pedersen | PQ-broken (binding) | ✅ | Lattice commitments |

---

## Known Limitations

### 1. STARK Proofs — Not Implemented

```
Status: SPECIFICATION ONLY
Risk: Light client verification requires working STARK implementation
Mitigation: Full nodes verify by recomputation until STARK ready
```

### 2. VDF Construction — Hash Chain

```
Type: Iterated hashing, not Wesolowski/Pietrzak
Sequentiality: Type C (empirical), not proven
Trade-off: Simpler but requires STARK for fast verification
```

### 3. NTP Server List — Unverified

```
Claim: 34 servers across 8 regions
Status: List specified, accessibility not verified
Risk: Some servers may be unreachable
```

### 4. Privacy Tiers — Quantum-Vulnerable

```
T2 (Pedersen): Binding quantum-vulnerable
T3 (Ring): ECDSA-based, quantum-vulnerable
Mitigation: Documented, upgrade paths specified
```

---

## What External Audit Should Verify

1. **Code-Spec Consistency** — Does implementation match specification?
2. **NTP Servers** — Are all 34 servers accessible and correct?
3. **VDF Timing** — Is 2²⁴ iterations actually ~2.5 seconds on reference hardware?
4. **Cryptographic Correctness** — SPHINCS+, ML-KEM, SHAKE256 usage
5. **Network Security** — P2P protocol, message authentication
6. **Privacy Claims** — T1/T2/T3 implementations

---

## Criticisms Already Addressed

### "ECVRF is quantum-vulnerable"

**Response:** Correct and documented. Accepted because:
- Eligibility proofs are ephemeral
- SPHINCS+ provides long-term security
- Upgrade path exists

### "VDF sequentiality is an assumption"

**Response:** Correct. Classified as Type C (empirical). Documented in Assumptions section with graceful degradation model.

### "Hash-chain VDF is not a 'real' VDF"

**Response:** Correct terminology concern. Montana uses iterated hashing with same sequentiality property as group-based VDFs, but different verification approach (STARK vs algebraic).

---

## Upgrade Triggers

| Component | Trigger | Action |
|-----------|---------|--------|
| ECVRF | NIST Lattice-VRF | Replace VRF |
| Pedersen | NIST Lattice commitment | Replace commitment |
| VDF iterations | Hardware speedup > 2x | Increase T |
| STARK | Implementation complete | Enable light verification |

---

## Summary

Montana v3.1 is a **design specification** with **partial implementation**. The design follows ATC layer constraints, but external audit is required to verify:

- Implementation correctness
- Security assumptions
- Infrastructure dependencies (NTP)
- Performance claims

**This document is self-assessment, not certification.**

---

*Montana v3.1 — Specification complete, implementation in progress, audit pending.*
