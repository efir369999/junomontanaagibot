# Time

A peer-to-peer electronic cash system based on time.

---

## Two Things

**Proof of Time** — the consensus protocol. VDF, Adonis, DAG.

**Time (Ɉ)** — the currency. 1 Ɉ = 1 second.

---

## The Currency: Ɉ

```
Symbol: Ɉ
Unit: 1 Ɉ = 1 second
Supply: 1,260,000,000 Ɉ (21 million minutes)
Block reward: 50 min → 25 min → 12.5 min → ...
Halving: every 210,000 blocks (~4 years)
Emission: 132 years
```

**Temporal Compression:** Reward ratio converges from 5:1 to 1:1. Inflation asymptotically approaches zero. Nash's Ideal Money realized.

---

## The Protocol: Proof of Time

Consensus based on time, not capital. Time cannot be bought, accelerated, or transferred.

### Dual Layer

**Layer 1 — Proof of History.** Sequential SHA-256 chain. Transaction ordering.

**Layer 2 — Proof of Time.** VDF checkpoints every 10 minutes. Finality.

### Leader Selection

ECVRF selects block producer. Probability proportional to Adonis score.

### Adonis Score

Five dimensions. All saturate.

| Dimension | Weight | Saturation |
|-----------|--------|------------|
| TIME | 50% | 180 days uptime |
| INTEGRITY | 20% | No violations |
| STORAGE | 15% | Full chain history |
| GEOGRAPHY | 10% | Location diversity |
| HANDSHAKE | 5% | Veteran trust bonds |

180 days = maximum influence. Capital irrelevant.

### DAG

1-8 parent references per block. PHANTOM ordering. Horizontal scaling.

---

## Privacy

| Tier | Hidden | Fee |
|------|--------|-----|
| T0 | Nothing | 1× |
| T1 | Receiver | 2× |
| T2 | + Amount | 5× |
| T3 | + Sender | 10× |

---

## Architecture

12 modules (Pantheon):

Chronos (VDF), Adonis (reputation), Hermes (P2P), Hades (storage), Athena (consensus), Prometheus (crypto), Mnemosyne (mempool), Plutus (wallet), Nyx (privacy), Themis (validation), Iris (RPC), Ananke (governance).

---

## Run

```bash
pip install pynacl
python node.py --run
```

---

## Documentation

| Document | Content |
|----------|---------|
| Time_v1.0.pdf | Whitepaper. Nash's Ideal Money. Temporal Compression. |
| ProofOfTime_v1.pdf | Technical specification. VDF. Adonis. DAG. |

---

## Comparison

| | Bitcoin | Ethereum | Time |
|---|---------|----------|------|
| Consensus | PoW | PoS | VDF |
| Influence | Hardware | Stake | Time |
| 51% attack | $20B | $10B | N × 180 days |

---

## Contact

alejandromontana@tutamail.com

---

Time is priceless. Now it has a price.

**Ɉ**
