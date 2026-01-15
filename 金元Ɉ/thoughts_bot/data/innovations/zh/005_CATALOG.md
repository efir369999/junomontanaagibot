# Montana创新目录

**总计:** 35项已实现的创新

---

## 共识 (7)

| # | 创新 | 文件 | 描述 |
|---|------|------|------|
| 1 | ACP | consensus.rs | 基于存在的共识 |
| 2 | 金元Ɉ | types.rs | 1 Ɉ → 1 秒 |
| 3 | 确定性抽签 | fork_choice.rs | seed = SHA3(prev ‖ τ₂) |
| 4 | 按权重分叉选择 | fork_choice.rs | ChainWeight |
| 5 | P2P证明 | consensus.rs | 签名传播 |
| 6 | 终结性 (Safe+Final) | finality.rs | 6切片 / τ₃ |
| 7 | 时间链 | types.rs | 哈希链排序 |

---

## 网络安全 (8)

| # | 创新 | 文件 | 描述 |
|---|------|------|------|
| 8 | 自适应冷却 | cooldown.rs | 按中位数1-180天 |
| 9 | 日蚀防护 | eviction.rs | 28+保护槽 |
| 10 | 地址管理器 | addrman.rs | 加密桶 |
| 11 | 驱逐策略 | eviction.rs | 多标准 |
| 12 | 令牌桶 | rate_limit.rs | 速率限制 |
| 13 | 流量控制 | connection.rs | 5MB接收 / 1MB发送 |
| 14 | 探测连接 | feeler.rs | 地址验证 |
| 15 | 阻止过滤器 | discouraged.rs | 滚动布隆 |

---

## 密码学 (6)

| # | 创新 | 文件 | 描述 |
|---|------|------|------|
| 16 | 后量子 | crypto.rs | ML-DSA-65, ML-KEM-768 |
| 17 | Noise XX + ML-KEM | noise.rs | 混合加密 |
| 18 | 域分离 | crypto.rs | 类型前缀 |
| 19 | 确定性签名 | crypto.rs | 无可塑性 |
| 20 | 时间预言机 | nts.rs, nmi.rs | 3层时间 |
| 21 | NTS/NTP | nts.rs | 90台服务器 |

---

## 架构 (5)

| # | 创新 | 文件 | 描述 |
|---|------|------|------|
| 22 | 节点层级 | consensus.rs | 80/20分配 |
| 23 | 时间切片 | types.rs | τ₁, τ₂, τ₃, τ₄ |
| 24 | 守护者委员会 | thoughts | 认知共识 |
| 25 | Montana ONE | MONTANA.md | 开放国家体验 |
| 26 | 三镜网络 | watchdog.py | 5节点 |

---

## 攻击防护 (9)

| # | 创新 | 文件 | 描述 |
|---|------|------|------|
| 27 | 时间扭曲防护 | layer_0.md | MTP + 未来限制 |
| 28 | 引导验证 | startup.rs | 1%容差 |
| 29 | 宽限期 | consensus.rs | 30秒 |
| 30 | 90%存在 | consensus.rs | 层级升级 |
| 31 | 减半 | types.rs | 210,000 τ₂ |
| 32 | MEV抵抗 | consensus.rs | 确定性tx_root |
| 33 | 硬编码认证 | hardcoded_identity.rs | 挑战-响应 |
| 34 | 自主权密钥 | consensus.rs | BIP-39本地 |
| 35 | presence_root | consensus.rs | 确定性Merkle |

---

## 核心公式

```
lim(evidence → ∞) 1 Ɉ → 1 秒
```

时间是唯一平等分配给所有人的资源。

---

```
Alejandro Montana
2026年1月
```
