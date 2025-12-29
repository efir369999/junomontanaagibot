# Pantheon

**12 gods. 24,000 lines. One protocol.**

---

## Architecture

```
                            CHRONOS
                         (VDF + PoH)
                              │
                              ▼
    HERMES ◄──────────► ATHENA ◄──────────► ADONIS
   (Network)          (Consensus)         (Reputation)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           HADES          THEMIS          PROMETHEUS
         (Storage)      (Validation)      (Crypto)
              │               │               │
              └───────────────┼───────────────┘
                              ▼
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           PLUTUS           NYX            IRIS
          (Wallet)       (Privacy)         (API)
```

---

## The Twelve

| # | God | Domain | Files | Lines | Status |
|---|-----|--------|-------|-------|--------|
| 1 | **Chronos** | Time Proofs | crypto.py, vdf_fast.py, poh.py | 5,400 | Active |
| 2 | **Adonis** | Reputation | adonis.py | 2,000 | Active |
| 3 | **Hermes** | P2P Network | network.py | 2,300 | Active |
| 4 | **Hades** | DAG Storage | database.py, dag_storage.py, dag.py | 3,100 | Active |
| 5 | **Athena** | Consensus | consensus.py, engine.py | 2,900 | Active |
| 6 | **Prometheus** | Cryptography | crypto.py | 2,300 | Active |
| 7 | **Mnemosyne** | Mempool | (integrated in node.py) | - | Integrated |
| 8 | **Plutus** | Wallet | wallet.py | 1,100 | Active |
| 9 | **Nyx** | Privacy | privacy.py, tiered_privacy.py, ristretto.py | 3,800 | Active |
| 10 | **Themis** | Validation | structures.py | 1,100 | Active |
| 11 | **Iris** | RPC/Dashboard | rpc.py, dashboard.py | 2,000 | Active |
| 12 | **Ananke** | Governance | - | - | Planned |

**Total: ~24,000 lines**

---

## Module Details

### Chronos — Time

```python
from pantheon.chronos import WesolowskiVDF, ECVRF, PoHChain
```

- **VDF**: Wesolowski (2048-bit RSA, 1M iterations)
- **VRF**: ECVRF on Ed25519
- **PoH**: SHA-256 hash chain (1 slot/second)

### Adonis — Reputation

```python
from pantheon.adonis import AdonisEngine, ReputationEvent
```

**Five Fingers:**
- THUMB (TIME): 50% — uptime, saturates at 180 days
- INDEX (INTEGRITY): 20% — no violations
- MIDDLE (STORAGE): 15% — chain history
- RING (GEOGRAPHY): 10% — country + city diversity
- PINKY (HANDSHAKE): 5% — mutual trust between veterans

### Hermes — Network

```python
from pantheon.hermes import P2PNetwork
```

- Noise Protocol XX encryption
- Peer discovery and gossip
- Block/transaction relay

### Hades — Storage

```python
from pantheon.hades import BlockDatabase, DAGStorage
```

- SQLite persistent storage
- DAG block structure (1-8 parents)
- PHANTOM-PoT ordering

### Athena — Consensus

```python
from pantheon.athena import ConsensusCalculator, ConsensusEngine
```

- ECVRF leader selection
- VDF checkpoint validation
- Finality after VDF proof

### Prometheus — Cryptography

```python
from pantheon.prometheus import ed25519_sign, sha256, rsa_keygen
```

- Ed25519 signatures
- SHA-256, BLAKE2b
- RSA-2048 for VDF

### Plutus — Wallet

```python
from pantheon.plutus import Wallet
```

- HD key derivation
- UTXO management
- Transaction building

### Nyx — Privacy

```python
from pantheon.nyx import StealthAddress, RingSignature, TieredPrivacy
```

**4 Tiers:**
- T0: Public (nothing hidden)
- T1: Stealth addresses (receiver hidden)
- T2: Pedersen commitments (amount hidden)
- T3: Ring signatures (sender hidden)

### Themis — Validation

```python
from pantheon.themis import Block, Transaction, validate_block
```

- Block structure definitions
- Transaction types
- Validation rules

### Iris — Interface

```python
from pantheon.iris import RPCServer, Dashboard
```

- JSON-RPC API
- WebSocket subscriptions
- Live dashboard

### Ananke — Governance

```
Status: Planned
```

- Protocol upgrades
- Parameter voting
- Emergency patches

---

## Usage

```python
from pantheon.chronos import WesolowskiVDF
from pantheon.adonis import AdonisEngine
from pantheon.athena import ConsensusCalculator

# Generate VDF proof
vdf = WesolowskiVDF()
proof = vdf.eval(challenge, iterations=1_000_000)

# Compute reputation
engine = AdonisEngine()
score = engine.compute_node_probability(pubkey, uptime, storage, total)

# Select leader
calc = ConsensusCalculator()
leader = calc.select_leader(nodes, seed)
```

---

## The Shortest Prompt

```
Proof of Time: Chronos proves, Athena selects, Adonis trusts.
```

---

*Time is the ultimate proof.*
