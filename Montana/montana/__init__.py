"""
Ɉ Montana: Temporal Time Unit v4.0

Mechanism for asymptotic trust in the value of time.
lim(evidence → ∞) 1 Ɉ → 1 second

Built on ATC Layer 3+.

v4.0: Security Stack (§30), unified naming, Lattice-VRF (Type B), ML-DSA, UTC finality.

Bootstrap server: 176.124.208.93:19656
"""

__version__ = "4.0.0"
__protocol_version__ = 11

from montana.constants import (
    PROJECT,
    SYMBOL,
    TICKER,
    TOTAL_SUPPLY,
    DEFAULT_PORT,
    PROTOCOL_VERSION,
)

# Core exports
from montana.core.types import Hash, PublicKey, NodeType, ParticipationTier, PrivacyTier
from montana.core.block import Block, BlockHeader
from montana.core.heartbeat import FullHeartbeat, LightHeartbeat
from montana.core.vdf import ClassGroupVDF as VDFComputer
from montana.core.vdf_accumulator import VDFAccumulator, FinalityLevel

# Crypto exports
from montana.crypto.hash import sha3_256, shake256
from montana.crypto.mldsa import mldsa_keygen as generate_mldsa_keypair

# Node exports
from montana.node.full_node import FullNode, FullNodeConfig
from montana.node.light_node import LightNode, LightNodeConfig

__all__ = [
    # Version
    "__version__",
    "__protocol_version__",
    # Constants
    "PROJECT",
    "SYMBOL",
    "TICKER",
    "TOTAL_SUPPLY",
    "DEFAULT_PORT",
    "PROTOCOL_VERSION",
    # Types
    "Hash",
    "PublicKey",
    "NodeType",
    "ParticipationTier",
    "PrivacyTier",
    # Core
    "Block",
    "BlockHeader",
    "FullHeartbeat",
    "LightHeartbeat",
    "VDFComputer",
    "VDFAccumulator",
    "FinalityLevel",
    # Crypto
    "sha3_256",
    "shake256",
    "generate_mldsa_keypair",
    # Nodes
    "FullNode",
    "FullNodeConfig",
    "LightNode",
    "LightNodeConfig",
]
