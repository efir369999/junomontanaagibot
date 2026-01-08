//! P2P message types with bounded collections (defense-in-depth)

use super::hardcoded_identity::{Challenge, CHALLENGE_SIZE};
use super::serde_safe::{
    BoundedVec, BoundedBytes,
    MAX_ADDRS, MAX_INV_ITEMS, MAX_HEADERS, MAX_PRESENCE_PROOFS,
    MAX_LOCATOR_HASHES, MAX_SIGNATURE_BYTES,
};
use super::types::{
    InvItem, NetAddress, RejectPayload, VersionPayload,
    MAX_VERSION_SIZE, MAX_ADDR_MSG_SIZE, MAX_INV_MSG_SIZE, MAX_HEADERS_SIZE,
    MAX_SLICE_SIZE, MAX_TX_SIZE, MAX_PRESENCE_SIZE, MAX_PING_SIZE, MAX_REJECT_SIZE,
    MESSAGE_SIZE_LIMIT,
};
use crate::crypto::mldsa::MLDSA65_SIG_SIZE;
use crate::types::{Hash, PresenceProof, Slice, SliceHeader, Transaction};
use serde::{Deserialize, Serialize};

pub const MAX_AUTH_CHALLENGE_SIZE: usize = CHALLENGE_SIZE + 16;
pub const MAX_AUTH_RESPONSE_SIZE: usize = MLDSA65_SIG_SIZE + MAX_VERSION_SIZE + 32;
pub const MAX_SIGNED_ADDR_SIZE: usize = MAX_ADDR_MSG_SIZE + MLDSA65_SIG_SIZE + 64;

/// Type aliases for bounded collections
pub type Addrs = BoundedVec<NetAddress, MAX_ADDRS>;
pub type InvItems = BoundedVec<InvItem, MAX_INV_ITEMS>;
pub type Headers = BoundedVec<SliceHeader, MAX_HEADERS>;
pub type PresenceProofs = BoundedVec<PresenceProof, MAX_PRESENCE_PROOFS>;
pub type LocatorHashes = BoundedVec<Hash, MAX_LOCATOR_HASHES>;
pub type Signature = BoundedBytes<MAX_SIGNATURE_BYTES>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Message {
    Version(VersionPayload),
    Verack,
    Addr(Addrs),
    GetAddr,
    Inv(InvItems),
    GetData(InvItems),
    NotFound(InvItems),
    Slice(Box<Slice>),
    GetSlice(u64),
    GetSlices { start: u64, count: u64 },
    SliceHeaders(Headers),
    GetHeaders { locator: LocatorHashes, stop: Hash },
    Presence(Box<PresenceProof>),
    GetPresence(u64),
    PresenceProofList(PresenceProofs),
    Tx(Box<Transaction>),
    Ping(u64),
    Pong(u64),
    Reject(RejectPayload),
    Mempool,
    FeeFilter(u64),
    AuthChallenge(Challenge),
    AuthResponse { version: VersionPayload, signature: Signature },
    SignedAddr { addrs: Addrs, signature: Signature },
}

impl Message {
    pub fn command(&self) -> &'static str {
        match self {
            Message::Version(_) => "version",
            Message::Verack => "verack",
            Message::Addr(_) => "addr",
            Message::GetAddr => "getaddr",
            Message::Inv(_) => "inv",
            Message::GetData(_) => "getdata",
            Message::NotFound(_) => "notfound",
            Message::Slice(_) => "slice",
            Message::GetSlice(_) => "getslice",
            Message::GetSlices { .. } => "getslices",
            Message::SliceHeaders(_) => "sliceheaders",
            Message::GetHeaders { .. } => "getheaders",
            Message::Presence(_) => "presence",
            Message::GetPresence(_) => "getpresence",
            Message::PresenceProofList(_) => "presenceproofs",
            Message::Tx(_) => "tx",
            Message::Ping(_) => "ping",
            Message::Pong(_) => "pong",
            Message::Reject(_) => "reject",
            Message::Mempool => "mempool",
            Message::FeeFilter(_) => "feefilter",
            Message::AuthChallenge(_) => "authchallenge",
            Message::AuthResponse { .. } => "authresponse",
            Message::SignedAddr { .. } => "signedaddr",
        }
    }

    pub fn allowed_pre_handshake(&self) -> bool {
        matches!(
            self,
            Message::Version(_)
                | Message::Verack
                | Message::Reject(_)
                | Message::AuthChallenge(_)
                | Message::AuthResponse { .. }
        )
    }

    pub fn estimated_size(&self) -> usize {
        match self {
            Message::Version(_) => 200,
            Message::Verack => 1,
            Message::Addr(addrs) => 4 + addrs.len() * 30,
            Message::GetAddr => 1,
            Message::Inv(items) => 4 + items.len() * 33,
            Message::GetData(items) => 4 + items.len() * 33,
            Message::NotFound(items) => 4 + items.len() * 33,
            Message::Slice(s) => 1000 + s.signature.len(),
            Message::GetSlice(_) => 8,
            Message::GetSlices { .. } => 16,
            Message::SliceHeaders(headers) => 4 + headers.len() * 200,
            Message::GetHeaders { locator, .. } => 4 + locator.len() * 32 + 32,
            Message::Presence(p) => 500 + p.signature.len(),
            Message::GetPresence(_) => 8,
            Message::PresenceProofList(proofs) => 4 + proofs.len() * 500,
            Message::Tx(tx) => 100 + tx.inputs.len() * 100 + tx.outputs.len() * 50,
            Message::Ping(_) => 8,
            Message::Pong(_) => 8,
            Message::Reject(r) => 10 + r.reason.len(),
            Message::Mempool => 1,
            Message::FeeFilter(_) => 8,
            Message::AuthChallenge(_) => CHALLENGE_SIZE,
            Message::AuthResponse { signature, .. } => 200 + signature.len(),
            Message::SignedAddr { addrs, signature } => 4 + addrs.len() * 30 + signature.len(),
        }
    }

    pub fn max_size_for_command(command: &str) -> usize {
        match command {
            "version" => MAX_VERSION_SIZE,
            "verack" => 16,
            "addr" => MAX_ADDR_MSG_SIZE,
            "getaddr" => 16,
            "inv" => MAX_INV_MSG_SIZE,
            "getdata" => MAX_INV_MSG_SIZE,
            "notfound" => MAX_INV_MSG_SIZE,
            "slice" => MAX_SLICE_SIZE,
            "getslice" => 32,
            "getslices" => 32,
            "sliceheaders" => MAX_HEADERS_SIZE,
            "getheaders" => MAX_HEADERS_SIZE,
            "presence" => MAX_PRESENCE_SIZE,
            "getpresence" => 32,
            "presenceproofs" => MAX_PRESENCE_SIZE * 100,
            "tx" => MAX_TX_SIZE,
            "ping" => MAX_PING_SIZE,
            "pong" => MAX_PING_SIZE,
            "reject" => MAX_REJECT_SIZE,
            "mempool" => 16,
            "feefilter" => 16,
            "authchallenge" => MAX_AUTH_CHALLENGE_SIZE,
            "authresponse" => MAX_AUTH_RESPONSE_SIZE,
            "signedaddr" => MAX_SIGNED_ADDR_SIZE,
            _ => MESSAGE_SIZE_LIMIT,
        }
    }

    pub fn validate_size(&self, actual_size: usize) -> bool {
        actual_size <= Self::max_size_for_command(self.command())
    }

    /// BoundedVec/BoundedBytes enforce limits at deserialization — always valid
    #[inline]
    pub fn validate_collection_sizes(&self) -> bool {
        true
    }
}
