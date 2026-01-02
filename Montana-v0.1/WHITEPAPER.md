# Ɉ Montana

**Version:** 3.2
**Date:** January 2026
**Ticker:** $MONT

---

> *"Time is the only resource distributed equally to all humans."*

---

## Abstract

**Ɉ Montana** is a mechanism for asymptotic trust in the value of time.

**Ɉ** is a **Temporal Time Unit** (TTU) — a unit that asymptotically approaches the definition:

```
lim(evidence → ∞) 1 Ɉ → 1 second
∀t: 1 Ɉ(t) ≈ 1 second
```

Montana builds trust in time value through the **Asymptotic Trust Consensus** (ATC) architecture — physical constraints, computational hardness, protocol primitives, and consensus mechanisms.

**Montana v3.2** is fully self-sovereign: no external blockchain dependencies, no external time sources. Finality is determined by UTC boundaries — time itself becomes the consensus mechanism.

The more evidence accumulates, the closer Ɉ approaches its definition. We never claim to arrive; we asymptotically approach.

---

## 1. Temporal Time Unit

### 1.1 Definition

```
Ɉ (Montana) — Temporal Time Unit

1 Ɉ     = 1 second
60 Ɉ    = 1 minute
3600 Ɉ  = 1 hour
86400 Ɉ = 1 day

Total Supply: 1,260,000,000 Ɉ = 21 million minutes
```

### 1.2 Why Time?

Time is unique among all quantities:

| Property | Time | Other Resources |
|----------|------|-----------------|
| **Distribution** | Equal (24h/day for everyone) | Unequal |
| **Creation** | Impossible | Possible |
| **Destruction** | Impossible | Possible |
| **Accumulation** | Limited by lifespan | Unlimited |
| **Measurement** | 10⁻¹⁹ precision (atomic) | Varies |
| **Universality** | Absolute | Relative |

**Time cannot be counterfeited.** Every second is physically verified by thermodynamics (irreversibility) and atomic physics (clock precision).

### 1.3 Purpose

Montana answers one question:

> **"Can we verify that one second has passed?"**

Yes — through:
1. **UTC boundaries** (universal time reference)
2. **VDF computation** (proof of participation in time window)
3. **Accumulated finality** (physics-based irreversibility)

---

## 2. Physical Foundation

### 2.1 Time Is Physical

The Temporal Time Unit rests on physics — constraints tested for 150+ years.

| Constraint | Implication | Precision |
|------------|-------------|-----------|
| **Thermodynamic Arrow** | Time flows one direction | 10⁻³¹⁵ reversal probability |
| **Atomic Universality** | All clocks of same isotope tick identically | 5.5×10⁻¹⁹ |
| **Speed of Light** | Maximum information transfer | 10⁻¹⁷ isotropy |
| **Landauer Limit** | Computation requires energy | Verified |

These are not assumptions. These are **the most precisely tested facts in science**.

### 2.2 Physical Guarantees

An adversary operating within known physics **cannot**:
- Reverse time (thermodynamics)
- Create time (conservation)
- Signal faster than light (relativity)
- Compute without energy (Landauer)
- **Advance UTC** (time is universal)

The TTU's integrity degrades only if physics requires revision at protocol-relevant scales.

### 2.3 Self-Sovereign Finality

Montana achieves finality through **UTC time boundaries** — deterministic points in time when blocks become final.

| Property | Guarantee |
|----------|-----------|
| Security basis | Physical (UTC is universal) |
| Attack cost | Cannot advance time |
| Dependencies | None (physics only) |
| Trust model | Physics |

**No hardware advantage can advance UTC. Time passes equally for all.**

---

## 3. UTC Finality Model

Montana uses UTC time boundaries for deterministic finality. No external time sources required — nodes use system UTC with ±5 second tolerance.

### 3.1 Finality Boundaries

```
UTC:     00:00  00:01  00:02  00:03  00:04  00:05  ...
           │      │      │      │      │      │
           ▼      ▼      ▼      ▼      ▼      ▼
        ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
        │ F0 │ │ F1 │ │ F2 │ │ F3 │ │ F4 │ │ F5 │
        └────┘ └────┘ └────┘ └────┘ └────┘ └────┘
           │      │
           │      └─ Finalizes blocks 00:00:00 - 00:00:59
           │
           └─ Genesis finality
```

Finality occurs every **1 minute** at UTC boundaries: 00:00, 00:01, 00:02, etc.

### 3.2 Time Consensus

```
Time source:        UTC on each node (system clock)
Tolerance:          ±5 seconds
External sources:   None required
```

Nodes accept blocks and heartbeats within ±5 seconds of their local UTC. This tolerance accommodates network propagation, minor drift, and NTP variance without requiring external synchronization.

### 3.3 VDF Role

VDF proves participation in a time window — not computation speed:

```
Node A (fast hardware):   VDF ready at 00:00:25 → waits → participates in F1
Node B (slow hardware):   VDF ready at 00:00:55 → participates in F1
Node C (too slow):        VDF ready at 00:01:02 → misses F1 → participates in F2
```

**Hardware advantage eliminated.** Fast hardware waits for UTC boundary like everyone else.

### 3.4 ASIC Resistance

| Scenario | Old Model (VDF depth) | UTC Model |
|----------|----------------------|-----------|
| ASIC vs CPU | 40x advantage | No advantage |
| Finality time | Variable (hardware-dependent) | Fixed (1 min UTC) |
| Attack vector | Faster VDF = more depth | None (cannot advance UTC) |

### 3.5 Clock Security

Montana relies on system UTC without external protocol-level synchronization. The ±5 second tolerance accommodates:

- Network propagation delay
- Minor clock drift
- NTP jitter

Nodes outside this window are not rejected by protocol — they simply fail to participate in the current finality window.

**Threat Model:**

| Attack | Target | Feasibility |
|--------|--------|-------------|
| Attack network time | All nodes | Impossible (UTC is physical) |
| Attack individual node | Single node | Requires OS compromise |

Clock manipulation attacks require compromising the victim's operating system time source. This is outside Montana's threat model, which assumes nodes maintain basic system integrity.

For high-value nodes, hardware security modules (HSM) with independent time sources provide additional protection.

---

## 4. Finality

```
┌─────────────────────────────────────────────────────────────────┐
│  HARD FINALITY (3 minutes)                                      │
│  3 UTC boundaries passed                                        │
│  Attack cost: Cannot reverse UTC                                │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  MEDIUM FINALITY (2 minutes)                                    │
│  2 UTC boundaries passed                                        │
│  High certainty                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  SOFT FINALITY (1 minute)                                       │
│  1 UTC boundary passed                                          │
│  Block included in finality checkpoint                          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Transaction Speed

```
00:00:00.000 — Transaction created
00:00:00.050 — In mempool
00:00:00.500 — Propagated to network
00:00:01.000 — Included in DAG (visible to all)
              ↓
      TRANSACTION VISIBLE AND ACTIVE
              ↓
00:01:00.000 — FINALIZED (irreversible)
```

| Stage | Time |
|-------|------|
| Transaction visibility | **< 1 second** |
| Finalization | **1 minute** |

Transactions are near-instant. Finalization is deterministic.

### 4.2 Finality Properties

| Property | UTC Finality |
|----------|--------------|
| Security | Physical (UTC is universal) |
| Attack cost | Impossible (cannot advance time) |
| Dependencies | None |
| Latency | Deterministic (1/2/3 minutes) |

### 4.3 Finality Checkpoint Structure

Each finality checkpoint (every 1 minute) contains:

```
Finality Checkpoint:
├─ UTC timestamp (boundary time)
├─ Merkle root of all blocks in window
├─ VDF proofs from participating nodes
├─ Aggregate signatures (SPHINCS+)
└─ Previous checkpoint hash
```

### 4.4 Network Partition

During network partition, both sides continue creating finality checkpoints independently.

```
Partition A (60% nodes)     Partition B (40% nodes)
        │                           │
00:01   F1-A (60 heartbeats)       F1-B (40 heartbeats)
00:02   F2-A                        F2-B
00:03   F3-A                        F3-B
        │                           │
        └─────── reconnect ─────────┘
                    │
               Fork choice
```

**Fork Choice Rule:** Heaviest checkpoint wins.

```python
def resolve_checkpoint_conflict(cp_a, cp_b):
    # Same UTC boundary
    assert cp_a.utc_timestamp == cp_b.utc_timestamp

    # Weight = number of valid heartbeats
    if len(cp_a.heartbeats) != len(cp_b.heartbeats):
        return max(cp_a, cp_b, key=lambda c: len(c.heartbeats))

    # Tiebreaker: lexicographically smaller hash
    return min(cp_a, cp_b, key=lambda c: c.hash)
```

**Consequences:**
- Transactions in smaller partition are NOT lost (DAG merge preserves blocks)
- Finality in smaller partition rolls back to reconnection point
- Heartbeats count after merge

| Scenario | Outcome |
|----------|---------|
| 60/40 split | Majority checkpoint canonical |
| 50/50 split | Smaller hash wins (deterministic) |
| Brief partition | Minimal impact (few checkpoints affected) |

---

## 5. Supply

### 5.1 Total

```
1,260,000,000 Ɉ = 21,000,000 minutes = 350,000 hours
```

A finite, human-comprehensible quantity of time.

### 5.2 Distribution

| Era | Per Block | Cumulative |
|-----|-----------|------------|
| 1 | 3,000 Ɉ (50 min) | 50% |
| 2 | 1,500 Ɉ (25 min) | 75% |
| 3 | 750 Ɉ (12.5 min) | 87.5% |
| ... | ... | ... |
| 33 | 1 Ɉ (1 sec) | 100% |

### 5.3 Zero Pre-allocation

```
PRE_ALLOCATION = 0
FOUNDER_UNITS = 0
RESERVED_UNITS = 0
```

All TTUs distributed through participation. No one starts with an advantage.

---

## 6. Participation

### 6.1 Node Types (2 only)

| Node Type | Storage | Tier |
|-----------|---------|------|
| **Full Node** | Full blockchain history (downloads all) | Tier 1 |
| **Light Node** | From connection moment only (mandatory) | Tier 2 |

### 6.2 Participation Tiers (3 only)

| Tier | Participants | Node Type | Lottery Weight |
|------|--------------|-----------|----------------|
| **1** | Full Node operators | Full Node | **70%** |
| **2** | Light Node operators OR Light Client owners | Light Node | **20%** |
| **3** | Light Client users | — | **10%** |

**Summary:**
- Tier 1 (Full Node): **70%** — network security
- Tier 2 (Light Node / Light Client): **20%** — infrastructure scaling
- Tier 3 (Light Client users): **10%** — mass adoption

### 6.3 Light Clients and Mass Adoption

Tier 2 and Tier 3 provide **barrier-free access** to time unit distribution through lightweight clients. Montana does not depend on any specific platform — it uses existing messaging and app platforms as distribution channels.

**Supported Light Client Platforms:**

| Platform | Type | Status |
|----------|------|--------|
| Telegram Bot | Messaging | Initial implementation |
| Discord Bot | Messaging | Planned |
| WeChat Mini Program | Messaging | Planned |
| iOS App (App Store) | Mobile | Planned |
| Android App (Google Play) | Mobile | Planned |
| Web Application | Browser | Planned |

**Design Principles:**

1. **Platform Independence:** Montana protocol has no dependency on Telegram or any platform. Light clients are interchangeable interfaces to the same network.

2. **Equal Conditions:** All participants compete on equal terms. The only arbiter is time — and time passes equally for everyone.

3. **Safe Scaling:** Tier 2+3 receive only 30% of lottery weight combined. This allows millions of participants without risk of network influence.

4. **No Sybil Advantage:** Creating multiple identities does not create more time. Each participant receives the same seconds per day regardless of account count.

```
Why 70/20/10 distribution?

Full Nodes (70%):    Provide security, store history, compute VDF
Light Nodes (20%):   Extend network reach, validate from connection
Light Clients (10%): Mass adoption, zero barrier entry

Security comes from Tier 1.
Scale comes from Tier 2+3.
```

**Time as the Universal Equalizer:**

```
Billionaire with 1000 accounts:  24 hours/day
Student with 1 account:          24 hours/day
Server farm with 10000 bots:     24 hours/day

No one can purchase more time.
No one can accelerate time.
Competition is healthy — the arbiter is physics.
```

### 6.4 Heartbeat

A **heartbeat** proves temporal presence within a finality window:

```
Full Heartbeat (Tier 1):       Light Heartbeat (Tier 2/3):
├─ VDF proof                   ├─ Timestamp (verified)
├─ Finality window reference   ├─ Source (LIGHT_NODE/TG_BOT/TG_USER)
└─ SPHINCS+ signature          ├─ Community ID
                               └─ SPHINCS+ signature
```

Heartbeats must arrive before UTC boundary to be included in finality checkpoint.

### 6.5 Score

```
Score = √(heartbeats)
```

Square root provides diminishing returns and Sybil resistance.

---

## 7. Technical

### 7.1 Post-Quantum Cryptography

| Function | Primitive | Standard |
|----------|-----------|----------|
| Signatures | SPHINCS+-SHAKE-128f | NIST FIPS 205 |
| Key Exchange | ML-KEM-768 | NIST FIPS 203 |
| Hashing | SHA3-256, SHAKE256 | NIST FIPS 202 |

### 7.2 VDF Parameters

```
VDF(input, T) = SHAKE256^T(input)

T = 2²⁴ iterations
Purpose: Proof of participation (not speed competition)
Verification: STARK proofs (O(log T))
```

VDF must complete before UTC boundary. Hardware that completes faster simply waits.

### 7.3 DAG Structure

```
    ┌─[B1]─┐
    │      │
[G]─┼─[B2]─┼─[B4]─...
    │      │
    └─[B3]─┘
```

No wasted work. All valid blocks included.

### 7.4 Privacy (Optional)

| Tier | Visibility |
|------|------------|
| T0 | Transparent |
| T1 | Hidden recipient |
| T2 | Hidden amount |
| T3 | Full privacy |

---

## 8. Epistemology

### 8.1 Asymptotic Trust

```
lim(evidence → ∞) Trust = 1
∀t: Trust(t) < 1

"We approach certainty; we never claim to reach it."
```

### 8.2 Classification

| Type | Meaning |
|------|---------|
| A | Proven theorem |
| B | Conditional proof |
| C | Empirical (10+ years) |
| P | Physical bound |
| N | Network-dependent |

Every claim is typed. This is epistemic honesty.

---

## 9. ATC Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3+: Montana — Temporal Time Unit                         │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Consensus (Safety, Liveness, UTC Finality)            │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Primitives (VDF, VRF, Commitment)                     │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: Computation (SHA-3, ML-KEM, SPHINCS+)                 │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│  Layer -1: Physics (Thermodynamics, Sequentiality, Light Speed) │
└─────────────────────────────────────────────────────────────────┘
```

**Montana v3.2:** Fully self-sovereign. No external dependencies.

---

## 10. Principle

**Ɉ Montana** is a mechanism for asymptotic trust in the value of time.

**Ɉ** is a Temporal Time Unit (TTU) that approaches — but never claims to reach — its definition:

```
lim(evidence → ∞) 1 Ɉ → 1 second
```

Like SI units define physical quantities through fundamental constants:
- **Second** → Cesium-133 hyperfine transition
- **Meter** → Speed of light
- **Kilogram** → Planck constant
- **Ɉ** → Asymptotically verified temporal passage

**Time is the universal constant. Ɉ Montana builds trust in its value.**

**Self-sovereign. Physics-based. No external dependencies.**

---

## References

- Einstein (1905, 1915) — Relativity
- Landauer (1961) — Computation thermodynamics
- Marshall et al. (2025) — Atomic clocks 5.5×10⁻¹⁹
- NIST FIPS 203/204/205 (2024) — Post-quantum cryptography
- Sompolinsky, Zohar (2018) — PHANTOM
- Boneh et al. (2018) — VDF
- ATC v10 — Layers -1, 0, 1, 2

---

## Parameters

```python
# Ɉ Montana
PROJECT = "Ɉ Montana"
SYMBOL = "Ɉ"
TICKER = "$MONT"
DEFINITION = "lim(evidence → ∞) 1 Ɉ → 1 second"
TOTAL_SUPPLY = 1_260_000_000

# Node Types (2 only)
NODE_TYPES = 2               # Full Node, Light Node

# Participation Tiers (3 only, numbered 1-2-3)
TIERS = 3                    # Tier 1, 2, 3
TIER_1_WEIGHT = 0.70         # Full Node → 70%
TIER_2_WEIGHT = 0.20         # Light Node / TG Bot owners → 20%
TIER_3_WEIGHT = 0.10         # TG Community users → 10%

# Time Consensus
TIME_TOLERANCE_SEC = 5       # ±5 seconds UTC tolerance
FINALITY_INTERVAL_SEC = 60   # 1 minute

# VDF (proof of participation)
VDF_ITERATIONS = 16_777_216  # 2^24

# Finality (UTC boundaries)
FINALITY_SOFT = 1            # 1 boundary (1 minute)
FINALITY_MEDIUM = 2          # 2 boundaries (2 minutes)
FINALITY_HARD = 3            # 3 boundaries (3 minutes)

# Distribution
PRE_ALLOCATION = 0
INITIAL_DISTRIBUTION = 3000  # Ɉ per block
HALVING_INTERVAL = 210_000
```

---

<div align="center">

**Ɉ Montana**

Mechanism for asymptotic trust in the value of time

*lim(evidence → ∞) 1 Ɉ → 1 second*

**Self-sovereign. Physics-based.**

**$MONT**

</div>
