# Presence-Verified Addresses

**Sybil-Resistant Peer Discovery**
**Version:** 1.0
**Date:** January 2026

---

## Abstract

Peer-to-peer networks face fundamental vulnerability to Eclipse and Sybil attacks through address manager poisoning. Traditional defenses rely on heuristics that can be circumvented by patient adversaries. This paper introduces Presence-Verified Addresses (PVA), which integrate Montana's temporal presence proofs into the peer discovery layer. By requiring addresses to demonstrate temporal presence before propagation, PVA transforms P2P layer security from heuristic to cryptographic.

---

## 1. Introduction

### 1.1 The Address Poisoning Problem

P2P networks maintain address databases (AddrMan) for peer discovery. Attackers can:

1. **Flood** the network with attacker-controlled addresses
2. **Eclipse** victims by surrounding them with malicious peers
3. **Time-travel** by providing addresses with manipulated timestamps

### 1.2 Existing Defenses

| Defense | Limitation |
|---------|------------|
| Timestamp validation | Attackers can use valid timestamps |
| Rate limiting | Slows but doesn't prevent poisoning |
| Netgroup bucketing | Determined attacker can populate all buckets |
| Connection diversity | Reactive, not preventive |

### 1.3 Core Insight

Montana's presence proofs provide exactly what address verification needs: unforgeable temporal commitment.

---

## 2. Presence-Verified Address Structure

### 2.1 Standard Address

```
addr = {
    ip: IPv4 or IPv6,
    port: uint16,
    services: uint64,
    timestamp: uint32
}
```

### 2.2 Presence-Verified Address

```
pva = {
    ip: IPv4 or IPv6,
    port: uint16,
    services: uint64,
    timestamp: uint32,
    presence_proof: {
        vdf_output: bytes32,
        vdf_proof: bytes,
        attestations: [peer_signatures],
        presence_duration: uint32
    },
    signature: bytes64
}
```

---

## 3. Verification Protocol

### 3.1 Acceptance Criteria

An address is accepted if and only if:

```python
def verify_pva(addr):
    # 1. Basic validity
    if not is_routable(addr.ip):
        return False

    # 2. Timestamp sanity
    if addr.timestamp > now() + 600:  # No future timestamps
        return False

    # 3. VDF verification
    if not verify_vdf(addr.presence_proof):
        return False

    # 4. Minimum presence
    if addr.presence_proof.presence_duration < MIN_PRESENCE:
        return False

    # 5. Attestation threshold
    if len(addr.presence_proof.attestations) < MIN_ATTESTATIONS:
        return False

    # 6. Signature validity
    if not verify_signature(addr):
        return False

    return True
```

### 3.2 Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| MIN_PRESENCE | 24 hours | Minimum temporal commitment |
| MIN_ATTESTATIONS | 3 | Byzantine fault tolerance |
| VDF_DIFFICULTY | 2^28 | ~10 minute computation |

---

## 4. Security Analysis

### 4.1 Time-Travel Attack

**Attack:** Submit address with future timestamp to gain priority.

**Defense:** VDF proof binds to block height, preventing timestamp manipulation:

```
vdf_input = H(block_hash || timestamp)
```

Future timestamps require predicting future blocks—computationally infeasible.

### 4.2 Mass Address Generation

**Attack:** Generate thousands of addresses to flood AddrMan.

**Defense:** Each address requires independent presence proof:

```
Cost(n addresses) = n × MIN_PRESENCE × infrastructure
                  = n × 24 hours × cost_per_node
```

1000 addresses require 1000 nodes running for 24+ hours.

### 4.3 Eclipse Attack

**Attack:** Surround victim with attacker-controlled peers.

**Defense:** PVA diversity requirement:

```python
def select_peers(candidates):
    selected = []
    presence_buckets = defaultdict(list)

    for addr in candidates:
        bucket = addr.presence_proof.presence_duration // DAY
        presence_buckets[bucket].append(addr)

    # Ensure diversity across presence durations
    for bucket in sorted(presence_buckets.keys(), reverse=True):
        selected.extend(presence_buckets[bucket][:MAX_PER_BUCKET])

    return selected[:MAX_PEERS]
```

---

## 5. Integration with Montana

### 5.1 Layered Architecture

```
┌─────────────────────────────────────┐
│         Application Layer           │
├─────────────────────────────────────┤
│         Consensus (ACP)             │
├─────────────────────────────────────┤
│    P2P Layer (Presence-Verified)    │  ← PVA operates here
├─────────────────────────────────────┤
│         Network Transport           │
└─────────────────────────────────────┘
```

### 5.2 Presence Proof Reuse

Addresses can reuse presence proofs from consensus participation:

```python
def create_pva(node):
    return PVA(
        ip=node.ip,
        port=node.port,
        presence_proof=node.consensus_presence_proof,  # Reuse!
        signature=sign(node.private_key)
    )
```

This creates virtuous cycle: consensus participation improves P2P reputation.

---

## 6. Performance

### 6.1 Overhead

| Operation | Standard Addr | PVA | Overhead |
|-----------|---------------|-----|----------|
| Size | 30 bytes | 150 bytes | 5× |
| Verification | 0.1ms | 10ms | 100× |
| Propagation | Immediate | After MIN_PRESENCE | 24h+ |

### 6.2 Justification

The overhead is acceptable because:

1. Address propagation is infrequent (once per node)
2. Security benefits outweigh latency costs
3. Verification parallelizes efficiently

---

## 7. Deployment

### 7.1 Gradual Rollout

```
Phase 1: Accept both standard and PVA addresses
Phase 2: Prefer PVA addresses in selection
Phase 3: Require PVA for new addresses
Phase 4: Deprecate standard addresses
```

### 7.2 Backward Compatibility

Legacy nodes continue functioning during transition:

```python
def process_addr(addr):
    if has_presence_proof(addr):
        return process_pva(addr)
    else:
        return process_legacy(addr)  # Deprecated path
```

---

## 8. Conclusion

Presence-Verified Addresses transform P2P address security from heuristic filtering to cryptographic verification. By requiring temporal presence before address acceptance, PVA eliminates entire classes of attacks that plague existing networks. The integration with Montana's consensus layer creates synergy: honest consensus participation directly improves network-level security.

---

## References

1. Heilman, E., et al. (2015). Eclipse Attacks on Bitcoin's Peer-to-Peer Network.
2. Marcus, Y., et al. (2018). Low-Resource Eclipse Attacks on Ethereum's Peer-to-Peer Network.
3. Montana, A. (2026). ACP Protocol Specification.

---

```
Alejandro Montana
Montana Protocol
January 2026
```
