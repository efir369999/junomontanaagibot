"""
Ɉ Montana DAG Consensus v3.1

Layer 2: PHANTOM Ordering per MONTANA_TECHNICAL_SPECIFICATION.md §10.

Implements DAG-based block structure with PHANTOM ordering,
using VDF weight instead of PoW for chain selection.

Key concepts:
- DAG allows concurrent block production (1-8 parents)
- PHANTOM identifies "blue set" of well-connected honest blocks
- VDF weight determines canonical chain
- Accumulated VDF provides finality
"""

from __future__ import annotations
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from enum import IntEnum
from collections import defaultdict

from montana.constants import (
    MAX_REORG_DEPTH,
    FINALITY_SOFT_CHECKPOINTS,
    FINALITY_MEDIUM_CHECKPOINTS,
    FINALITY_HARD_CHECKPOINTS,
)
from montana.core.types import Hash
from montana.core.block import Block, BlockHeader

logger = logging.getLogger(__name__)


# DAG Parameters
MAX_PARENTS = 8
MIN_PARENTS = 1
PHANTOM_K = 8  # Anticone threshold for blue set


class BlockFinalityState(IntEnum):
    """
    Block finality state machine per §6.

    State transitions are one-way (increasing finality only):
    PENDING → TENTATIVE → CONFIRMED → FINALIZED → IRREVERSIBLE

    States:
    - PENDING: Block just received, no VDF confirmations
    - TENTATIVE: 1+ VDF checkpoints (soft finality, ~2.5s)
    - CONFIRMED: 100+ VDF checkpoints (medium finality, ~4min)
    - FINALIZED: 1000+ VDF checkpoints (hard finality, ~40min)
    - IRREVERSIBLE: Cannot be reorged under any circumstances
    """
    PENDING = 0
    TENTATIVE = 1
    CONFIRMED = 2
    FINALIZED = 3
    IRREVERSIBLE = 4


@dataclass
class DAGNode:
    """
    Node in the DAG representing a block.

    Tracks block metadata and DAG relationships.
    """
    block_hash: Hash
    header: BlockHeader
    parent_hashes: Tuple[Hash, ...]
    vdf_weight: int                          # Accumulated VDF iterations
    is_blue: bool = False                    # In PHANTOM blue set
    blue_score: int = 0                      # Blue ancestors count
    finality_state: BlockFinalityState = BlockFinalityState.PENDING
    vdf_checkpoints: int = 0                 # Accumulated VDF checkpoints


class PHANTOMOrdering:
    """
    PHANTOM protocol adapted for Montana VDF-based consensus.

    Identifies "blue set" of well-connected honest blocks,
    then orders blocks by cumulative VDF weight.

    Algorithm:
    1. For each block B, compute anticone(B) = blocks neither ancestor nor descendant
    2. Block B is "blue" if |anticone(B) ∩ blue_set| ≤ k
    3. Order blue blocks by cumulative VDF weight descending
    4. Insert red blocks between their blue ancestors and descendants
    """

    def __init__(self, k: int = PHANTOM_K):
        self.k = k

        # DAG structure
        self.nodes: Dict[Hash, DAGNode] = {}              # hash -> node
        self.children: Dict[Hash, Set[Hash]] = defaultdict(set)  # hash -> child hashes
        self.tips: Set[Hash] = set()                      # Current DAG tips

        # Blue set
        self.blue_set: Set[Hash] = set()

        # Ordering cache
        self._ordered_blocks: Optional[List[Hash]] = None
        self._order_dirty: bool = True

        # Finality tracking
        self.irreversible_blocks: Set[Hash] = set()

        # Orphan pool (blocks with unknown parents)
        self.orphans: Dict[Hash, Block] = {}
        self.orphan_by_parent: Dict[Hash, Set[Hash]] = defaultdict(set)

        self._lock = threading.RLock()

    def add_block(self, block: Block) -> bool:
        """
        Add block to DAG.

        Returns True if block was added successfully.
        Blocks with unknown parents are added to orphan pool.
        """
        with self._lock:
            block_hash = block.hash()

            if block_hash in self.nodes:
                return False

            # Check if all parents exist
            missing_parents = []
            for parent in block.parent_hashes:
                if parent != Hash.zero() and parent not in self.nodes:
                    missing_parents.append(parent)

            # If missing parents, add to orphan pool
            if missing_parents:
                self.orphans[block_hash] = block
                for parent in missing_parents:
                    self.orphan_by_parent[parent].add(block_hash)
                logger.debug(
                    f"Block {block_hash.hex()[:16]} added to orphan pool, "
                    f"waiting for {len(missing_parents)} parents"
                )
                return False

            # Calculate VDF weight
            parent_weights = []
            for parent in block.parent_hashes:
                if parent in self.nodes:
                    parent_weights.append(self.nodes[parent].vdf_weight)
            vdf_weight = max(parent_weights, default=0) + block.header.vdf_iterations

            # Create DAG node
            node = DAGNode(
                block_hash=block_hash,
                header=block.header,
                parent_hashes=block.parent_hashes,
                vdf_weight=vdf_weight,
            )
            self.nodes[block_hash] = node

            # Update children relationships
            for parent in block.parent_hashes:
                if parent in self.tips:
                    self.tips.remove(parent)
                self.children[parent].add(block_hash)

            # New block is a tip
            self.tips.add(block_hash)

            # Update blue set
            self._update_blue_set(block_hash)

            # Check if any orphans can now be processed
            self._process_orphans(block_hash)

            # Invalidate ordering cache
            self._order_dirty = True

            logger.debug(
                f"Added block {block_hash.hex()[:16]} "
                f"(height={block.height}, parents={len(block.parent_hashes)}, "
                f"weight={vdf_weight}, blue={node.is_blue})"
            )

            return True

    def _process_orphans(self, new_block_hash: Hash) -> int:
        """Process orphans that were waiting for this block."""
        added = 0
        waiting = self.orphan_by_parent.pop(new_block_hash, set())

        for orphan_hash in waiting:
            if orphan_hash not in self.orphans:
                continue

            orphan = self.orphans.pop(orphan_hash)

            # Clean up other parent references
            for parent in orphan.parent_hashes:
                if parent in self.orphan_by_parent:
                    self.orphan_by_parent[parent].discard(orphan_hash)

            # Try to add again
            if self.add_block(orphan):
                added += 1
                logger.debug(f"Orphan {orphan_hash.hex()[:16]} resolved")

        return added

    def _get_ancestors(self, block_hash: Hash) -> Set[Hash]:
        """Get all ancestors of a block."""
        ancestors = set()
        queue = list(self.nodes[block_hash].parent_hashes)

        while queue:
            parent = queue.pop()
            if parent in ancestors or parent == Hash.zero():
                continue
            if parent not in self.nodes:
                continue
            ancestors.add(parent)
            queue.extend(self.nodes[parent].parent_hashes)

        return ancestors

    def _get_descendants(self, block_hash: Hash) -> Set[Hash]:
        """Get all descendants of a block."""
        descendants = set()
        queue = list(self.children[block_hash])

        while queue:
            child = queue.pop()
            if child in descendants:
                continue
            descendants.add(child)
            queue.extend(self.children[child])

        return descendants

    def _get_anticone(self, block_hash: Hash) -> Set[Hash]:
        """
        Get anticone of a block.

        Anticone(B) = blocks that are neither ancestors nor descendants of B.
        """
        ancestors = self._get_ancestors(block_hash)
        descendants = self._get_descendants(block_hash)

        anticone = set()
        for h in self.nodes:
            if h != block_hash and h not in ancestors and h not in descendants:
                anticone.add(h)

        return anticone

    def _update_blue_set(self, block_hash: Hash):
        """
        Update blue set after adding a block.

        Block B is blue if |anticone(B) ∩ blue_set| ≤ k
        """
        anticone = self._get_anticone(block_hash)
        blue_anticone = anticone & self.blue_set

        node = self.nodes[block_hash]

        if len(blue_anticone) <= self.k:
            self.blue_set.add(block_hash)
            node.is_blue = True

            # Compute blue score
            parent_scores = [
                self.nodes[p].blue_score
                for p in node.parent_hashes
                if p in self.nodes
            ]
            node.blue_score = max(parent_scores, default=0) + 1
        else:
            node.is_blue = False

    def get_ordered_blocks(self) -> List[Hash]:
        """
        Get topologically ordered blocks using PHANTOM ordering.

        1. Order blue blocks by cumulative VDF weight descending
        2. Insert red blocks between their blue ancestors and descendants
        """
        with self._lock:
            if not self._order_dirty and self._ordered_blocks is not None:
                return self._ordered_blocks

            # Separate blue and red blocks
            blue_blocks = [(self.nodes[h].vdf_weight, h) for h in self.blue_set]
            red_blocks = [h for h in self.nodes if h not in self.blue_set]

            # Sort blue blocks by VDF weight (descending)
            blue_blocks.sort(reverse=True)
            blue_order = [h for _, h in blue_blocks]

            # Insert red blocks
            ordered = []
            blue_index = {h: i for i, h in enumerate(blue_order)}

            for blue_hash in blue_order:
                ordered.append(blue_hash)

                # Find red blocks that should come after this blue block
                for red_hash in red_blocks:
                    red_node = self.nodes[red_hash]

                    should_insert = False
                    for parent in red_node.parent_hashes:
                        if parent == blue_hash:
                            should_insert = True
                            break
                        if parent in blue_index and blue_index[parent] <= blue_index.get(blue_hash, 0):
                            should_insert = True
                            break

                    if should_insert and red_hash not in ordered:
                        ordered.append(red_hash)

            # Add any remaining red blocks
            for red_hash in red_blocks:
                if red_hash not in ordered:
                    ordered.append(red_hash)

            self._ordered_blocks = ordered
            self._order_dirty = False

            return ordered

    def get_tips(self) -> List[Hash]:
        """Get current DAG tips."""
        with self._lock:
            return list(self.tips)

    def get_node(self, block_hash: Hash) -> Optional[DAGNode]:
        """Get DAG node by hash."""
        return self.nodes.get(block_hash)

    def is_blue(self, block_hash: Hash) -> bool:
        """Check if block is in blue set."""
        return block_hash in self.blue_set

    def get_main_chain(self) -> List[Hash]:
        """
        Get the main chain of blue blocks from genesis to tip.

        The main chain follows the path with highest cumulative VDF weight.
        """
        with self._lock:
            if not self.nodes:
                return []

            # Find genesis (block with no parents in DAG)
            genesis = None
            for h, node in self.nodes.items():
                has_known_parent = False
                for p in node.parent_hashes:
                    if p in self.nodes:
                        has_known_parent = True
                        break
                if not has_known_parent:
                    genesis = h
                    break

            if genesis is None:
                return []

            # Build main chain by following highest-weight path
            chain = [genesis]
            current = genesis

            while True:
                child_hashes = self.children.get(current, set())
                if not child_hashes:
                    break

                # Select child with highest VDF weight in blue set
                best_child = None
                best_weight = -1

                for child_hash in child_hashes:
                    node = self.nodes.get(child_hash)
                    if node and child_hash in self.blue_set:
                        if node.vdf_weight > best_weight:
                            best_weight = node.vdf_weight
                            best_child = child_hash

                # If no blue child, take any child with highest weight
                if best_child is None:
                    for child_hash in child_hashes:
                        node = self.nodes.get(child_hash)
                        if node and node.vdf_weight > best_weight:
                            best_weight = node.vdf_weight
                            best_child = child_hash

                if best_child is None:
                    break

                chain.append(best_child)
                current = best_child

            return chain

    def get_finality_state(self, block_hash: Hash) -> BlockFinalityState:
        """Get finality state of a block."""
        node = self.nodes.get(block_hash)
        if node is None:
            return BlockFinalityState.PENDING
        return node.finality_state

    def update_finality(self, block_hash: Hash, vdf_checkpoints: int) -> BlockFinalityState:
        """
        Update block finality based on accumulated VDF checkpoints.

        Args:
            block_hash: Block to update
            vdf_checkpoints: Total VDF checkpoints accumulated

        Returns:
            New finality state
        """
        with self._lock:
            node = self.nodes.get(block_hash)
            if node is None:
                return BlockFinalityState.PENDING

            node.vdf_checkpoints = vdf_checkpoints
            old_state = node.finality_state

            # Determine new state based on VDF checkpoints
            if vdf_checkpoints >= FINALITY_HARD_CHECKPOINTS:
                node.finality_state = BlockFinalityState.FINALIZED
                self.irreversible_blocks.add(block_hash)
            elif vdf_checkpoints >= FINALITY_MEDIUM_CHECKPOINTS:
                node.finality_state = max(node.finality_state, BlockFinalityState.CONFIRMED)
            elif vdf_checkpoints >= FINALITY_SOFT_CHECKPOINTS:
                node.finality_state = max(node.finality_state, BlockFinalityState.TENTATIVE)

            if node.finality_state != old_state:
                logger.info(
                    f"Block {block_hash.hex()[:16]} finality: "
                    f"{old_state.name} → {node.finality_state.name} "
                    f"({vdf_checkpoints} checkpoints)"
                )

            return node.finality_state

    def can_reorg(self, block_hash: Hash) -> bool:
        """
        Check if a block can be reorganized.

        Blocks in IRREVERSIBLE state cannot be reorged.
        """
        return block_hash not in self.irreversible_blocks

    def resolve_fork(
        self,
        chain_a: List[Hash],
        chain_b: List[Hash],
    ) -> List[Hash]:
        """
        Resolve fork between two chains.

        Uses Montana rules:
        1. Chain with more blue blocks wins
        2. If equal, chain with higher cumulative VDF weight wins
        3. If still equal, lexicographically lower tip hash wins
        """
        with self._lock:
            # Count blue blocks
            blue_a = sum(1 for h in chain_a if h in self.blue_set)
            blue_b = sum(1 for h in chain_b if h in self.blue_set)

            if blue_a > blue_b:
                return chain_a
            elif blue_b > blue_a:
                return chain_b

            # Equal blue count, compare VDF weight
            weight_a = sum(self.nodes[h].vdf_weight for h in chain_a if h in self.nodes)
            weight_b = sum(self.nodes[h].vdf_weight for h in chain_b if h in self.nodes)

            if weight_a > weight_b:
                return chain_a
            elif weight_b > weight_a:
                return chain_b

            # Equal weight, use lexicographic tie-breaker
            tip_a = chain_a[-1] if chain_a else Hash.zero()
            tip_b = chain_b[-1] if chain_b else Hash.zero()

            return chain_a if tip_a.data < tip_b.data else chain_b

    def get_confirmation_depth(self, block_hash: Hash) -> int:
        """Get confirmation depth (number of descendants in main chain)."""
        with self._lock:
            main_chain = self.get_main_chain()
            if block_hash not in main_chain:
                return 0

            idx = main_chain.index(block_hash)
            return len(main_chain) - idx - 1

    def compute_reorg(
        self,
        new_tip: Hash,
    ) -> Tuple[List[Hash], List[Hash]]:
        """
        Compute blocks to disconnect and connect for reorg to new_tip.

        Respects finality: IRREVERSIBLE blocks cannot be disconnected.

        Returns:
            (blocks_to_disconnect, blocks_to_connect)
            Empty lists if reorg is rejected
        """
        with self._lock:
            current_chain = self.get_main_chain()
            if not current_chain:
                return ([], [new_tip] if new_tip in self.nodes else [])

            # Find common ancestor
            new_ancestors = self._get_ancestors(new_tip) | {new_tip}

            common_ancestor = None
            for block_hash in reversed(current_chain):
                if block_hash in new_ancestors:
                    common_ancestor = block_hash
                    break

            if common_ancestor is None:
                # Complete reorg - check for irreversible blocks
                for block_hash in current_chain:
                    if block_hash in self.irreversible_blocks:
                        logger.warning(
                            f"Reorg rejected: would disconnect IRREVERSIBLE block "
                            f"{block_hash.hex()[:16]}"
                        )
                        return ([], [])
                return (current_chain, [new_tip])

            # Blocks to disconnect
            disconnect_idx = current_chain.index(common_ancestor) + 1
            to_disconnect = current_chain[disconnect_idx:]

            # Check for irreversible blocks
            for block_hash in to_disconnect:
                if block_hash in self.irreversible_blocks:
                    logger.warning(
                        f"Reorg rejected: would disconnect IRREVERSIBLE block "
                        f"{block_hash.hex()[:16]}"
                    )
                    return ([], [])

            # Check reorg depth
            if len(to_disconnect) > MAX_REORG_DEPTH:
                logger.warning(
                    f"Reorg rejected: depth {len(to_disconnect)} exceeds "
                    f"MAX_REORG_DEPTH {MAX_REORG_DEPTH}"
                )
                return ([], [])

            # Blocks to connect
            to_connect = []
            current = new_tip
            while current != common_ancestor and current in self.nodes:
                to_connect.insert(0, current)
                parents = self.nodes[current].parent_hashes
                if parents and parents[0] in self.nodes:
                    current = parents[0]
                else:
                    break

            return (to_disconnect, to_connect)

    def get_stats(self) -> Dict:
        """Get DAG statistics."""
        with self._lock:
            return {
                "total_blocks": len(self.nodes),
                "blue_blocks": len(self.blue_set),
                "tips": len(self.tips),
                "orphans": len(self.orphans),
                "irreversible": len(self.irreversible_blocks),
            }
