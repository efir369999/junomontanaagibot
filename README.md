# ATC: Asymptotic Trust Consensus

### Physics-First Protocol Architecture

> **Trust that approaches certainty — grounded in physical law, not faith in algorithms.**

```
                                    ╭─────────────────────────── 1.0 (certainty)
         Trust                     ╱
           ↑                    ╱
       1.0 ┤              ══════
           │          ════╯
           │       ═══╯        ← You are here: 10⁻¹⁷ — 10⁻¹⁹ precision
           │    ═══╯
           │  ══╯
           │══╯
       0.0 ┼────────────────────────────────────────→ Evidence

           lim(evidence → ∞) Trust = 1
           ∀t: Trust(t) < 1

           "We approach, we never claim to arrive."
```

[![Layer -1](https://img.shields.io/badge/Layer%20--1-v2.1-blue)](ATC%20v8.1/Layer%20-1/layer_minus_1.md)
[![Layer 0](https://img.shields.io/badge/Layer%200-v1.0-blue)](ATC%20v8.1/Layer%200/layer_0.md)
[![Layer 1](https://img.shields.io/badge/Layer%201-v1.1-blue)](ATC%20v8.1/Layer%201/layer_1.md)
[![Rating](https://img.shields.io/badge/rating-10%2F10-brightgreen)](ATC%20v8.1/Layer%20-1/HYPERCRITICISM_PROOF.md)
[![Physics](https://img.shields.io/badge/foundation-physics-orange)](ATC%20v8.1/Layer%20-1/layer_minus_1.md)

---

## The One-Liner

**ATC is a protocol architecture where security proofs begin with physics, not assumptions.**

---

## Why Physics First?

```
Traditional Cryptography:          ATC Architecture:

"Secure if P ≠ NP"                 Layer -1: Physics      ← IMPOSSIBLE
       ↓                                  ↓
  (unproven)                       Layer 0:  Computation  ← HARD
       ↓                                  ↓
"Trust us"                         Layer 1+: Protocol     ← SECURE
```

**The difference:**
- Traditional: Security hangs on unproven mathematical conjectures
- ATC: Security is rooted in experimentally verified physical law

**If P = NP tomorrow:**
- Traditional crypto: Everything breaks
- ATC: Physical bounds still hold — Landauer, Bekenstein, light speed

---

## The Layer Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2+: Protocols (Montana, etc.)               [Future]    │
│  ─────────────────────────────────────────────────────────────  │
│  Consensus mechanisms, network models, cryptocurrencies        │
└─────────────────────────────────────────────────────────────────┘
                              ↑ builds on
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Protocol Primitives                        v1.1      │
│  ─────────────────────────────────────────────────────────────  │
│  What is BUILDABLE: VDF, VRF, Commitment, Timestamp, Ordering  │
│  Types: A/B/C/P (inherited) + S (composition) + I (impl)       │
└─────────────────────────────────────────────────────────────────┘
                              ↑ builds on
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: Computational Constraints                   v1.0     │
│  ─────────────────────────────────────────────────────────────  │
│  What is HARD: OWF, Lattice, CRHF, VDF, NIST PQC              │
│  Types: A (proven) → B (reduction) → C (empirical) → D (conjecture)
└─────────────────────────────────────────────────────────────────┘
                              ↑ builds on
┌─────────────────────────────────────────────────────────────────┐
│  Layer -1: Physical Constraints                       v2.1     │
│  ─────────────────────────────────────────────────────────────  │
│  What is IMPOSSIBLE: Thermodynamics, Light speed, Landauer    │
│  Precision: 10⁻¹⁷ — 10⁻¹⁹ | Tested: 150+ years               │
└─────────────────────────────────────────────────────────────────┘
                              ↑ builds on
┌─────────────────────────────────────────────────────────────────┐
│  ██████████████████  PHYSICAL REALITY  ██████████████████████  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Insight

> **Any adversary operates within known physics.**

This is the minimal assumption required for "security" to be meaningful.

An adversary unconstrained by physics could:
- Reverse entropy (undo any computation)
- Signal faster than light (violate causality)
- Store infinite information (break all bounds)
- Violate mathematical axioms themselves

**We don't assume P ≠ NP. We assume physics.**

---

## Layer -1: Physical Constraints

*What is IMPOSSIBLE — tested to 10⁻¹⁷ precision*

| ID | Constraint | Evidence |
|----|------------|----------|
| L-1.1 | Thermodynamic Arrow | 150+ years, no macroscopic violation |
| L-1.2 | Atomic Time | 5.5×10⁻¹⁹ (Marshall et al. 2025) |
| L-1.3 | Landauer Limit | Experimentally approached |
| L-1.4 | Speed of Light | 10⁻¹⁷ isotropy (GPS continuous) |
| L-1.5 | Time Uniformity | mm-scale optical clocks |
| L-1.6 | Bekenstein Bound | Indirect (GR + QM) |
| L-1.7 | Thermal Noise | Confirmed since 1928 |
| L-1.8 | Decoherence | Many scales confirmed |

**→ [Full specification](ATC%20v8.1/Layer%20-1/layer_minus_1.md)**

---

## Layer 0: Computational Constraints

*What is HARD — given that physics holds*

| Tier | Content | Stability |
|------|---------|-----------|
| 1 | Information-theoretic (Shannon, Birthday) | Eternal |
| 2 | Physical bounds (Landauer → computation) | 100+ years |
| 3 | Hardness classes (OWF, Lattice, CRHF) | 50+ years |
| 4 | Primitives (SHA-3, ML-KEM, ML-DSA) | 10-30 years |

**Post-Quantum Ready:** NIST FIPS 203/204/205 from day one.

**→ [Full specification](ATC%20v8.1/Layer%200/layer_0.md)**

---

## Layer 1: Protocol Primitives

*What is BUILDABLE — cryptographic building blocks*

| Primitive | Description | PQ Status |
|-----------|-------------|-----------|
| VDF | Verifiable Delay Functions | Hash-based: Secure |
| VRF | Verifiable Random Functions | Lattice: Secure |
| Commitment | Hide-then-reveal schemes | Hash-based: Secure |
| Timestamp | Temporal existence proofs | Hash-based: Secure |
| Ordering | Event sequencing (Lamport, DAG) | Math only (no crypto) |

**Types:** A/B/C/P (inherited) + S (composition) + I (implementation)

**→ [Full specification](ATC%20v8.1/Layer%201/layer_1.md)**

---

## Asymptotic — Not Absolute

| What we claim | What we don't claim |
|---------------|---------------------|
| Maximal empirical confidence | Metaphysical certainty |
| 150+ years of verification | Eternal truth |
| 10⁻¹⁷ precision | Infinite precision |
| Best current physics | Final physics |

**This is the asymptote:**
- We approach certainty
- We never claim to reach it
- Each year of non-violation brings us closer
- We remain epistemically honest

---

## Repository Structure

```
ATC v8.1/
├── Layer -1/                      Physical Constraints (v2.1)
│   ├── layer_minus_1.md               Specification
│   ├── HYPERCRITICISM_PROOF.md        Certification
│   ├── EVALUATION_QUICK_REFERENCE.md  Assessment card
│   └── RELEASE_v2.1.md                Release notes
│
├── Layer 0/                       Computational Constraints (v1.0)
│   ├── layer_0.md                     Specification
│   ├── HYPERCRITICISM_PROOF.md        Certification
│   ├── EVALUATION_QUICK_REFERENCE.md  Assessment card
│   └── RELEASE_v1.0.md                Release notes
│
└── Layer 1/                       Protocol Primitives (v1.1)
    ├── layer_1.md                     Specification + Implementation Appendix
    ├── HYPERCRITICISM_PROOF.md        Certification
    ├── EVALUATION_QUICK_REFERENCE.md  Assessment card
    └── RELEASE_v1.1.md                Release notes

CLAUDE.md                          AI Architect role definition
```

---

## Quick Links

| Document | Layer | Description |
|----------|-------|-------------|
| [Layer -1 Spec](ATC%20v8.1/Layer%20-1/layer_minus_1.md) | -1 | Physical constraints |
| [Layer 0 Spec](ATC%20v8.1/Layer%200/layer_0.md) | 0 | Computational constraints |
| [Layer 1 Spec](ATC%20v8.1/Layer%201/layer_1.md) | 1 | Protocol primitives |
| [L-1 Certification](ATC%20v8.1/Layer%20-1/HYPERCRITICISM_PROOF.md) | -1 | Why 10/10 |
| [L0 Certification](ATC%20v8.1/Layer%200/HYPERCRITICISM_PROOF.md) | 0 | Why 10/10 |
| [L1 Certification](ATC%20v8.1/Layer%201/HYPERCRITICISM_PROOF.md) | 1 | Why 10/10 |

---

## The Name Explained

```
A S Y M P T O T I C
        ↓
    Approaching but never reaching
    Honest about limits
    Scientific humility

T R U S T
    ↓
    Not blind faith
    Earned through evidence
    Grounded in physics

C O N S E N S U S
        ↓
    Scientific community (NIST, BIPM, PTB)
    Cryptographic community (IACR, NIST PQC)
    Network participants
```

**ATC = The protocol that earns trust asymptotically, through physics.**

---

## Releases

| Layer | Version | Tag | Status |
|-------|---------|-----|--------|
| -1 | v2.1.0 | [layer-1-v2.1.0](https://github.com/afgrouptime/atc/releases/tag/layer-1-v2.1.0) | 10/10 |
| 0 | v1.0.0 | [layer-0-v1.0.0](https://github.com/afgrouptime/atc/releases/tag/layer-0-v1.0.0) | 10/10 |
| 1 | v1.1.0 | [layer-1-v1.1.0](https://github.com/afgrouptime/atc/releases/tag/layer-1-v1.1.0) | 10/10 + 100% impl |

---

## Foundational References

**Physics (Layer -1):**
- Einstein (1905, 1915) — Relativity
- Landauer (1961) — Computation thermodynamics
- Bekenstein (1981) — Information bounds
- Marshall et al. (2025) — Atomic clocks at 10⁻¹⁹

**Computation (Layer 0):**
- Shannon (1948) — Information theory
- NIST FIPS 203/204/205 (2024) — Post-quantum standards
- Regev (2005) — Lattice cryptography

**Protocol Primitives (Layer 1):**
- Boneh et al. (2018) — Verifiable Delay Functions
- Micali et al. (1999) — Verifiable Random Functions
- Lamport (1978) — Time, Clocks, and Ordering

---

## License

MIT License

---

## Closing Principle

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   "Protocols may assume weaker physics (additional constraints);│
│    they cannot assume stronger physics (fewer constraints)     │
│    without leaving the domain of known science."               │
│                                                                │
│                              — Layer -1, Closing Principle     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

<div align="center">

*Dedicated to the memory of*

**Hal Finney** (1956–2014)

*First recipient of a Bitcoin transaction. Creator of RPOW.*

*"Running bitcoin" — January 11, 2009*

---

**ATC: Where security begins with physics.**

</div>
