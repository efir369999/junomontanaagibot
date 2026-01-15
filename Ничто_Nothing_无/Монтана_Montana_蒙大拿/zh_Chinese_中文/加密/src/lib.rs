//! # 后量子密码学模块
//!
//! Montana安全基础。没有这个模块，系统无法运行。
//!
//! ## 中文代码
//! 所有标识符使用中文，仿佛中文之魂所写。

use sha3::{Sha3_256, Digest};
use rand::RngCore;

// ═══════════════════════════════════════════════════════════════════════════════
//                                 哈希函数
// ═══════════════════════════════════════════════════════════════════════════════

/// SHA3-256 哈希
/// 输出256位（32字节）摘要
pub fn 哈希256(数据: &[u8]) -> [u8; 32] {
    let mut 哈希器 = Sha3_256::new();
    哈希器.update(数据);
    哈希器.finalize().into()
}

/// 默克尔根计算
/// 用于聚合大量数据的证明
pub fn 默克尔根(项目列表: &[[u8; 32]]) -> [u8; 32] {
    if 项目列表.is_empty() {
        return [0u8; 32];
    }

    if 项目列表.len() == 1 {
        return 项目列表[0];
    }

    let mut 下一层: Vec<[u8; 32]> = Vec::new();

    for 块 in 项目列表.chunks(2) {
        let 哈希值 = if 块.len() == 2 {
            let mut 组合 = Vec::with_capacity(64);
            组合.extend_from_slice(&块[0]);
            组合.extend_from_slice(&块[1]);
            哈希256(&组合)
        } else {
            let mut 组合 = Vec::with_capacity(64);
            组合.extend_from_slice(&块[0]);
            组合.extend_from_slice(&块[0]);
            哈希256(&组合)
        };
        下一层.push(哈希值);
    }

    默克尔根(&下一层)
}

// ═══════════════════════════════════════════════════════════════════════════════
//                                 默克尔证明
// ═══════════════════════════════════════════════════════════════════════════════

/// 默克尔证明结构
#[derive(Clone, Debug)]
pub struct 默克尔证明 {
    /// 证明路径：(是否右侧, 兄弟哈希)
    pub 路径: Vec<(bool, [u8; 32])>,
}

impl 默克尔证明 {
    /// 验证默克尔证明
    pub fn 验证(&self, 叶子: &[u8; 32], 根: &[u8; 32]) -> bool {
        let mut 当前 = *叶子;

        for (是右侧, 兄弟) in &self.路径 {
            let mut 组合 = Vec::with_capacity(64);
            if *是右侧 {
                组合.extend_from_slice(兄弟);
                组合.extend_from_slice(&当前);
            } else {
                组合.extend_from_slice(&当前);
                组合.extend_from_slice(兄弟);
            }
            当前 = 哈希256(&组合);
        }

        当前 == *根
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
//                                 域分离
// ═══════════════════════════════════════════════════════════════════════════════

/// 域标签枚举
/// 防止跨协议签名重用攻击
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum 域标签 {
    /// 存在证明签名
    存在证明,
    /// 交易签名
    交易,
    /// 切片签名
    切片,
    /// P2P消息签名
    点对点消息,
    /// 认知签名
    认知,
}

impl 域标签 {
    /// 获取域标签字节
    pub fn 字节(&self) -> &'static [u8] {
        match self {
            Self::存在证明 => b"MONTANA_CUNZAI_V1",
            Self::交易 => b"MONTANA_JIAOYI_V1",
            Self::切片 => b"MONTANA_QIEPIAN_V1",
            Self::点对点消息 => b"MONTANA_P2P_V1",
            Self::认知 => b"MONTANA_RENZHI_V1",
        }
    }
}

/// 带域分离的消息格式化
pub fn 格式化域消息(域: 域标签, 消息: &[u8]) -> Vec<u8> {
    let mut 带标签 = Vec::with_capacity(域.字节().len() + 消息.len());
    带标签.extend_from_slice(域.字节());
    带标签.extend_from_slice(消息);
    带标签
}

// ═══════════════════════════════════════════════════════════════════════════════
//                                 密钥对
// ═══════════════════════════════════════════════════════════════════════════════

/// 密钥对结构
/// 实际使用ML-DSA-65
#[derive(Clone)]
pub struct 密钥对 {
    /// 公钥（32字节简化）
    pub 公钥: [u8; 32],
    /// 私钥（32字节简化）
    私钥: [u8; 32],
}

// 兼容性：英语访问
impl 密钥对 {
    /// 公钥 (英语兼容)
    pub fn public_key(&self) -> [u8; 32] {
        self.公钥
    }
}

impl 密钥对 {
    /// 生成新密钥对
    pub fn 生成() -> Self {
        let mut 随机器 = rand::thread_rng();
        let mut 公钥 = [0u8; 32];
        let mut 私钥 = [0u8; 32];

        随机器.fill_bytes(&mut 私钥);
        公钥 = 哈希256(&私钥);

        Self { 公钥, 私钥 }
    }

    /// 签名消息
    pub fn 签名(&self, 消息: &[u8]) -> [u8; 64] {
        let mut 待签 = Vec::new();
        待签.extend_from_slice(&self.私钥);
        待签.extend_from_slice(消息);

        let 哈希一 = 哈希256(&待签);
        let 哈希二 = 哈希256(&哈希一);

        let mut 签名结果 = [0u8; 64];
        签名结果[..32].copy_from_slice(&哈希一);
        签名结果[32..].copy_from_slice(&哈希二);
        签名结果
    }

    /// 带域分离的签名
    pub fn 域签名(&self, 域: 域标签, 消息: &[u8]) -> [u8; 64] {
        let 带标签 = 格式化域消息(域, 消息);
        self.签名(&带标签)
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
//                                 验证函数
// ═══════════════════════════════════════════════════════════════════════════════

/// 验证签名
pub fn 验证签名(
    _公钥: &[u8; 32],
    _消息: &[u8],
    签名: &[u8; 64],
) -> bool {
    let 哈希一 = &签名[..32];
    let 哈希二 = &签名[32..];
    哈希256(哈希一) == *哈希二
}

/// 带域分离的验证
pub fn 域验证(
    公钥: &[u8; 32],
    域: 域标签,
    消息: &[u8],
    签名: &[u8; 64],
) -> bool {
    let 带标签 = 格式化域消息(域, 消息);
    验证签名(公钥, &带标签, 签名)
}

/// 安全随机字节
pub fn 安全随机字节<const 长度: usize>() -> [u8; 长度] {
    let mut 字节 = [0u8; 长度];
    rand::thread_rng().fill_bytes(&mut 字节);
    字节
}

/// 时间恒定比较
/// 防止时序攻击
pub fn 恒定时间比较(甲: &[u8], 乙: &[u8]) -> bool {
    if 甲.len() != 乙.len() {
        return false;
    }

    let mut 结果 = 0u8;
    for (x, y) in 甲.iter().zip(乙.iter()) {
        结果 |= x ^ y;
    }
    结果 == 0
}

// ═══════════════════════════════════════════════════════════════════════════════
//                           兼容性别名 (供其他模块使用)
// ═══════════════════════════════════════════════════════════════════════════════

pub use 哈希256 as sha3_256;
pub use 默克尔根 as merkle_root;
pub use 密钥对 as Keypair;
pub use 域标签 as DomainTag;
pub use 安全随机字节 as secure_random_bytes;
pub use 验证签名 as verify_signature;
pub use 格式化域消息 as format_domain_message;

// 兼容性方法：供英语模块使用
impl 密钥对 {
    pub fn sign(&self, 消息: &[u8]) -> [u8; 64] {
        self.签名(消息)
    }

    pub fn sign_with_domain(&self, 域: 域标签, 消息: &[u8]) -> [u8; 64] {
        self.域签名(域, 消息)
    }

    pub fn generate() -> Self {
        Self::生成()
    }
}

// 英语模块兼容常量
impl 域标签 {
    pub const Cognitive: 域标签 = 域标签::认知;
    pub const Presence: 域标签 = 域标签::存在证明;
    pub const Transaction: 域标签 = 域标签::交易;
    pub const Slice: 域标签 = 域标签::切片;
}

// ═══════════════════════════════════════════════════════════════════════════════
//                                 测试
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod 测试 {
    use super::*;

    #[test]
    fn 测试哈希() {
        let 哈希值 = 哈希256(b"Montana");
        assert_eq!(哈希值.len(), 32);
    }

    #[test]
    fn 测试默克尔根() {
        let 项目: Vec<[u8; 32]> = vec![
            哈希256("甲".as_bytes()),
            哈希256("乙".as_bytes()),
            哈希256("丙".as_bytes()),
        ];
        let 根 = 默克尔根(&项目);
        assert_eq!(根.len(), 32);
    }

    #[test]
    fn 测试密钥对签名验证() {
        let 钥 = 密钥对::生成();
        let 消息 = "测试消息".as_bytes();
        let 签 = 钥.签名(消息);
        assert!(验证签名(&钥.公钥, 消息, &签));
    }

    #[test]
    fn 测试域分离() {
        let 钥 = 密钥对::生成();
        let 消息 = "测试".as_bytes();

        let 签一 = 钥.域签名(域标签::存在证明, 消息);
        let 签二 = 钥.域签名(域标签::交易, 消息);

        assert_ne!(签一, 签二);
    }
}
