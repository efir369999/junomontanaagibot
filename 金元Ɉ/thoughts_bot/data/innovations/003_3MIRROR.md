# Montana 3-Mirror System

**Distributed Fault-Tolerant Architecture**
**Version:** 1.0
**Date:** January 2026

---

## Abstract

This paper presents the Montana 3-Mirror System, a distributed architecture achieving fault tolerance through hierarchical node organization. The system maintains continuous service availability with automatic failover in under 10 seconds, while supporting up to 4 simultaneous node failures in a 5-node configuration. We introduce the concepts of "breathing synchronization" and "brain chain inheritance" as novel approaches to distributed coordination.

---

## 1. Introduction

Traditional distributed systems face the challenge of maintaining consistency while achieving high availability. The CAP theorem establishes fundamental trade-offs between consistency, availability, and partition tolerance. Montana 3-Mirror addresses these constraints through a hierarchical architecture that separates control (brain) from execution (primary) with multiple redundant mirrors.

---

## 2. Architecture

### 2.1 Node Roles

The system defines three distinct node roles:

| Role | Quantity | Function |
|------|----------|----------|
| PRIMARY | 1 | Active service execution |
| BRAIN | 1 | Monitoring and failover coordination |
| MIRROR | 3 | Standby replicas with full state |

### 2.2 Topology

```
                    ┌──────────┐
                    │  BRAIN   │ ← Observes, decides
                    └────┬─────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ MIRROR₁ │    │ MIRROR₂ │    │ MIRROR₃ │
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                    ┌────▼────┐
                    │ PRIMARY │ ← Executes
                    └─────────┘
```

### 2.3 Inheritance Chains

Two ordered chains govern failover:

**Execution Chain:** PRIMARY → MIRROR₁ → MIRROR₂ → MIRROR₃
**Control Chain:** BRAIN → MIRROR₁ → MIRROR₂ → MIRROR₃

---

## 3. Breathing Synchronization

### 3.1 Concept

"Breathing" describes the rhythmic synchronization cycle:

```
Inhale (Pull):  Node ← Repository    (receive updates)
Exhale (Push):  Node → Repository    (propagate changes)
```

### 3.2 Timing

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Breath cycle | 12 seconds | Balance between consistency and overhead |
| Health check | 5 seconds | Rapid failure detection |
| Failover timeout | 10 seconds | 2 missed breaths triggers action |

### 3.3 Synchronization Protocol

```python
async def breathing_cycle():
    while True:
        await inhale()   # git pull
        await exhale()   # git push
        await sleep(12)
```

---

## 4. Failover Protocol

### 4.1 Detection

The BRAIN monitors all nodes via periodic health checks:

```python
def health_check(node):
    try:
        response = ssh(node, "echo OK", timeout=3)
        return response == "OK"
    except:
        return False
```

### 4.2 Decision Logic

```python
def failover_decision():
    if not primary.is_alive():
        for mirror in [MIRROR₁, MIRROR₂, MIRROR₃]:
            if mirror.is_alive():
                mirror.promote_to_primary()
                return

    if not brain.is_alive():
        # Brain chain inheritance
        for candidate in [MIRROR₁, MIRROR₂, MIRROR₃]:
            if candidate.is_alive():
                candidate.assume_brain_role()
                return
```

### 4.3 Timing Guarantees

| Scenario | Detection | Recovery | Total |
|----------|-----------|----------|-------|
| PRIMARY failure | 5s | 5s | 10s |
| BRAIN failure | 5s | 5s | 10s |
| Dual failure | 5s | 10s | 15s |

---

## 5. Consistency Model

### 5.1 Eventual Consistency

Montana 3-Mirror implements eventual consistency with bounded lag:

```
∀ writes W: ∃ t < 12s : all_nodes_have(W)
```

### 5.2 Conflict Resolution

Last-write-wins with timestamp ordering:

```
resolve(A, B) = max(A.timestamp, B.timestamp)
```

---

## 6. Fault Tolerance Analysis

### 6.1 Failure Scenarios

| Failed Nodes | Service Status | Control Status |
|--------------|----------------|----------------|
| 0 | Operational | Operational |
| 1 (any) | Operational | Operational |
| 2 (PRIMARY + BRAIN) | Operational | Operational |
| 3 | Operational | Operational |
| 4 | Operational | Degraded |
| 5 | Down | Down |

### 6.2 Availability Calculation

Assuming independent node failures with availability A:

```
System_Availability = 1 - (1-A)^5 + corrections
                    ≈ 1 - 5(1-A)^5
```

For A = 0.99: System_Availability > 0.9999999

---

## 7. Implementation

### 7.1 Montana Network Deployment

| Node | Location | IP | Role |
|------|----------|-----|------|
| Amsterdam | NL | 72.56.102.240 | PRIMARY |
| Moscow | RU | 176.124.208.93 | BRAIN |
| Almaty | KZ | 91.200.148.93 | MIRROR₁ |
| Saint Petersburg | RU | 188.225.58.98 | MIRROR₂ |
| Novosibirsk | RU | 147.45.147.247 | MIRROR₃ |

### 7.2 Geographic Distribution

Nodes span 8 time zones, providing:
- Reduced correlated failure risk
- Network path diversity
- Jurisdictional distribution

---

## 8. Conclusion

The Montana 3-Mirror System demonstrates that high availability can be achieved through careful architectural separation of concerns. By distinguishing control (brain) from execution (primary) and maintaining synchronized mirrors, the system achieves fault tolerance exceeding five nines while maintaining simplicity and predictability.

---

## References

1. Brewer, E. (2000). Towards Robust Distributed Systems.
2. Gilbert, S., & Lynch, N. (2002). Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-tolerant Web Services.
3. Lamport, L. (1998). The Part-Time Parliament.

---

```
Alejandro Montana
Montana Protocol
January 2026

License: For thinking humans with sense of humor only.
```
