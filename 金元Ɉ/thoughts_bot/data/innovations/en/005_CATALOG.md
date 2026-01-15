# Montana Innovations Catalog

**Total:** 35 implemented innovations

---

## Consensus (7)

| # | Innovation | File | Description |
|---|------------|------|-------------|
| 1 | ACP | consensus.rs | Presence-Based Consensus |
| 2 | 金元Ɉ | types.rs | 1 Ɉ → 1 second |
| 3 | Deterministic lottery | fork_choice.rs | seed = SHA3(prev ‖ τ₂) |
| 4 | Fork-choice by weight | fork_choice.rs | ChainWeight |
| 5 | P2P attestation | consensus.rs | Signature gossip |
| 6 | Finality (Safe+Final) | finality.rs | 6 slices / τ₃ |
| 7 | Timechain | types.rs | Hash-chain ordering |

---

## Network Security (8)

| # | Innovation | File | Description |
|---|------------|------|-------------|
| 8 | Adaptive Cooldown | cooldown.rs | 1-180 days by median |
| 9 | Eclipse protection | eviction.rs | 28+ protected slots |
| 10 | AddrMan | addrman.rs | Crypto buckets |
| 11 | Eviction policy | eviction.rs | Multi-criteria |
| 12 | Token bucket | rate_limit.rs | Rate limiting |
| 13 | Flow control | connection.rs | 5MB recv / 1MB send |
| 14 | Feeler connections | feeler.rs | Address validation |
| 15 | Discouraged filter | discouraged.rs | Rolling bloom |

---

## Cryptography (6)

| # | Innovation | File | Description |
|---|------------|------|-------------|
| 16 | Post-Quantum | crypto.rs | ML-DSA-65, ML-KEM-768 |
| 17 | Noise XX + ML-KEM | noise.rs | Hybrid encryption |
| 18 | Domain separation | crypto.rs | Type prefix |
| 19 | Deterministic signatures | crypto.rs | No malleability |
| 20 | Time Oracle | nts.rs, nmi.rs | 3 time layers |
| 21 | NTS/NTP | nts.rs | 90 servers |

---

## Architecture (5)

| # | Innovation | File | Description |
|---|------------|------|-------------|
| 22 | Node tiers | consensus.rs | 80/20 split |
| 23 | Time slices | types.rs | τ₁, τ₂, τ₃, τ₄ |
| 24 | Guardian Council | thoughts | Cognitive consensus |
| 25 | Montana ONE | MONTANA.md | Open Nation Experience |
| 26 | 3-Mirror Network | watchdog.py | 5 nodes |

---

## Attack Protection (9)

| # | Innovation | File | Description |
|---|------------|------|-------------|
| 27 | Time-warp protection | layer_0.md | MTP + Future limit |
| 28 | Bootstrap verify | startup.rs | 1% tolerance |
| 29 | Grace period | consensus.rs | 30 sec |
| 30 | 90% presence | consensus.rs | Tier upgrade |
| 31 | Halving | types.rs | 210,000 τ₂ |
| 32 | MEV-resistance | consensus.rs | Deterministic tx_root |
| 33 | Hardcoded auth | hardcoded_identity.rs | Challenge-Response |
| 34 | Self-sovereign keys | consensus.rs | BIP-39 local |
| 35 | presence_root | consensus.rs | Deterministic Merkle |

---

## Key Formula

```
lim(evidence → ∞) 1 Ɉ → 1 second
```

Time is the only resource distributed equally among all.

---

```
Alejandro Montana
January 2026
```
