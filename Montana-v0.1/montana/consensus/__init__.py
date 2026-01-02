"""
Ɉ Montana Consensus Module v3.1

DAG-based consensus with PHANTOM ordering and VDF-weighted finality.
"""

from montana.consensus.dag import (
    PHANTOMOrdering,
    BlockFinalityState,
)

__all__ = [
    "PHANTOMOrdering",
    "BlockFinalityState",
]
