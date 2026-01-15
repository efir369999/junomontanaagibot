# Каталог инноваций Montana

**Всего:** 35 реализованных инноваций

---

## Консенсус (7)

| # | Инновация | Файл | Описание |
|---|-----------|------|----------|
| 1 | ACP | consensus.rs | Presence-Based Consensus |
| 2 | 金元Ɉ | types.rs | 1 Ɉ → 1 секунда |
| 3 | Детерминированная лотерея | fork_choice.rs | seed = SHA3(prev ‖ τ₂) |
| 4 | Fork-choice по весу | fork_choice.rs | ChainWeight |
| 5 | P2P аттестация | consensus.rs | Gossip подписей |
| 6 | Finality (Safe+Final) | finality.rs | 6 слайсов / τ₃ |
| 7 | Таймчейн | types.rs | Hash-chain ordering |

---

## Безопасность сети (8)

| # | Инновация | Файл | Описание |
|---|-----------|------|----------|
| 8 | Adaptive Cooldown | cooldown.rs | 1-180 дней по медиане |
| 9 | Eclipse protection | eviction.rs | 28+ защищённых слотов |
| 10 | AddrMan | addrman.rs | Крипто-бакеты |
| 11 | Eviction policy | eviction.rs | Многокритериальный |
| 12 | Token bucket | rate_limit.rs | Rate limiting |
| 13 | Flow control | connection.rs | 5МБ recv / 1МБ send |
| 14 | Feeler connections | feeler.rs | Валидация адресов |
| 15 | Discouraged filter | discouraged.rs | Rolling bloom |

---

## Криптография (6)

| # | Инновация | Файл | Описание |
|---|-----------|------|----------|
| 16 | Post-Quantum | crypto.rs | ML-DSA-65, ML-KEM-768 |
| 17 | Noise XX + ML-KEM | noise.rs | Гибридное шифрование |
| 18 | Domain separation | crypto.rs | Prefix по типу |
| 19 | Детерминированные подписи | crypto.rs | Без malleability |
| 20 | Time Oracle | nts.rs, nmi.rs | 3 слоя времени |
| 21 | NTS/NTP | nts.rs | 90 серверов |

---

## Архитектура (5)

| # | Инновация | Файл | Описание |
|---|-----------|------|----------|
| 22 | Тиры узлов | consensus.rs | 80/20 split |
| 23 | Таймслайсы | types.rs | τ₁, τ₂, τ₃, τ₄ |
| 24 | Guardian Council | thoughts | Когнитивный консенсус |
| 25 | Montana ONE | MONTANA.md | Open Nation Experience |
| 26 | 3-Mirror Network | watchdog.py | 5 узлов |

---

## Защита от атак (9)

| # | Инновация | Файл | Описание |
|---|-----------|------|----------|
| 27 | Time-warp защита | layer_0.md | MTP + Future limit |
| 28 | Bootstrap verify | startup.rs | 1% толерантность |
| 29 | Grace period | consensus.rs | 30 сек |
| 30 | 90% presence | consensus.rs | Апгрейд тира |
| 31 | Halving | types.rs | 210,000 τ₂ |
| 32 | MEV-resistance | consensus.rs | tx_root детерминирован |
| 33 | Hardcoded auth | hardcoded_identity.rs | Challenge-Response |
| 34 | Self-sovereign keys | consensus.rs | BIP-39 локально |
| 35 | presence_root | consensus.rs | Детерминированный Merkle |

---

## Ключевая формула

```
lim(evidence → ∞) 1 Ɉ → 1 секунда
```

Время — единственный ресурс, распределённый одинаково между всеми.

---

```
Alejandro Montana
Январь 2026
```
