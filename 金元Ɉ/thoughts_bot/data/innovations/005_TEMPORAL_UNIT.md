# The Temporal Unit Ɉ

**A New Measure of Value**
**Version:** 1.0
**Date:** January 2026

---

## Abstract

This paper introduces Ɉ (Unicode U+0248), a unit of value derived from proven temporal presence. Unlike fiat currencies backed by government decree or cryptocurrencies backed by computational work, Ɉ represents verified time—the only resource distributed equally among all humans. We formalize the relationship between Ɉ and physical time, establishing the asymptotic equivalence: lim(evidence → ∞) 1 Ɉ → 1 second.

---

## 1. Introduction

### 1.1 The Problem of Value

Every monetary system requires a basis for value. Historical approaches include:

- **Commodity money:** Value from intrinsic utility (gold, silver)
- **Fiat money:** Value from legal mandate (USD, EUR)
- **Cryptocurrency:** Value from computational scarcity (BTC)

Each system has fundamental limitations:

| System | Limitation |
|--------|------------|
| Commodity | Unequal distribution of resources |
| Fiat | Arbitrary inflation by central authority |
| Crypto (PoW) | Favors hardware owners, wastes energy |
| Crypto (PoS) | Favors capital holders, plutocratic |

### 1.2 Time as Foundation

Time possesses unique properties as a value basis:

1. **Universal distribution:** Every human receives 24 hours daily
2. **Non-transferable:** Cannot be given, stolen, or purchased
3. **Non-storable:** Must be "spent" as it arrives
4. **Irreversible:** Cannot be recovered once passed

---

## 2. Definition of Ɉ

### 2.1 Symbol Specification

| Attribute | Value |
|-----------|-------|
| Symbol | Ɉ |
| Unicode | U+0248 (Latin Capital Letter J with Stroke) |
| Origin | J from Junona project (22.08.2022) |
| Visual | J with two horizontal strokes |
| Color | Gold (#D4A84B) on Black (#000000) |

### 2.2 Formal Definition

**Definition 1.** One Ɉ represents one second of cryptographically verified temporal presence.

```
1 Ɉ ≡ Proof(Δt = 1 second)
```

### 2.3 Asymptotic Property

As evidence accumulates, Ɉ converges to physical seconds:

```
lim(evidence → ∞) 1 Ɉ → 1 second

where evidence = {VDF_proofs, NTS_attestations, peer_confirmations}
```

This is asymptotic—perfect equivalence requires infinite verification.

---

## 3. Issuance Mechanism

### 3.1 Emission Schedule

Ɉ is issued through presence proof submission:

| Parameter | Value | Description |
|-----------|-------|-------------|
| τ₂ (slice) | 10 minutes | Minimum presence interval |
| T4 (window) | 40 minutes | Emission window |
| Emission rate | 1% per slice | Distribution per interval |
| Total supply | 1,260,000,000 Ɉ | Maximum supply |

### 3.2 Distribution Formula

Within each slice, emission distributes proportionally to presence:

```
reward(participant) = emission_rate × (presence_weight / total_weight)

where presence_weight = f(messages, characters, attestations)
```

### 3.3 Halving Schedule

Emission halves every 210,000 τ₂ intervals (≈4 years):

```
emission(epoch) = initial_emission / 2^epoch
```

---

## 4. Economic Properties

### 4.1 Natural Scarcity

Unlike artificial scarcity (mining difficulty), Ɉ scarcity derives from physics:

```
Max_Ɉ_per_person_per_day = 86,400 (seconds in day)
```

No technology can exceed this limit.

### 4.2 Equal Opportunity

The wealthy cannot purchase more time:

```
Ɉ_earning_potential(billionaire) = Ɉ_earning_potential(student)
                                  = 86,400 Ɉ/day (theoretical max)
```

### 4.3 Inflation Resistance

Ɉ supply is mathematically bounded:

```
∑(all_Ɉ_ever) ≤ 1,260,000,000 Ɉ
```

No entity can inflate supply.

---

## 5. Philosophical Foundation

### 5.1 Time as Universal Currency

> "Time is the only resource distributed equally among all people."

This principle underlies Ɉ's design. While wealth, talent, and opportunity vary, every human receives identical temporal allocation.

### 5.2 Presence as Proof of Life

Ɉ measures not computation or capital, but presence—the fundamental act of existing through time. Each Ɉ earned represents a moment lived and cryptographically attested.

### 5.3 Value from Attention

Economic value ultimately derives from human attention, which is bounded by time. Ɉ directly measures this attention.

---

## 6. Implementation

### 6.1 Storage

```
balance = {
    "address": public_key_hash,
    "amount": Ɉ_quantity,
    "last_presence": timestamp,
    "total_presence": cumulative_seconds
}
```

### 6.2 Transfer

```
transfer(from, to, amount):
    require(balances[from] >= amount)
    balances[from] -= amount
    balances[to] += amount
    emit Transfer(from, to, amount)
```

### 6.3 Verification

```
verify_Ɉ(amount, proof):
    vdf_valid = verify_vdf(proof.vdf_output, proof.vdf_proof)
    time_valid = proof.duration >= amount
    sig_valid = verify_signature(proof.signature, proof.pubkey)
    return vdf_valid && time_valid && sig_valid
```

---

## 7. Comparison

| Property | BTC | ETH | Ɉ |
|----------|-----|-----|---|
| Basis | Computation | Stake | Time |
| Distribution | Unequal (hardware) | Unequal (capital) | Equal (time) |
| Energy | High | Medium | Low |
| Maximum supply | 21M | Unlimited | 1.26B |
| Minimum unit | 1 satoshi | 1 wei | 1 Ɉ |

---

## 8. Conclusion

Ɉ represents a fundamental reconceptualization of value: not as stored labor or captured computation, but as proven temporal presence. By grounding value in the one resource common to all humans, Ɉ achieves natural fairness without sacrificing scarcity or security.

---

## References

1. Szabo, N. (2002). Shelling Out: The Origins of Money.
2. Nakamoto, S. (2008). Bitcoin: A Peer-to-Peer Electronic Cash System.
3. Montana, A. (2026). Atemporal Coordinate Presence.

---

```
Alejandro Montana
Montana Protocol
January 2026

lim(evidence → ∞) 1 Ɉ → 1 second
```
