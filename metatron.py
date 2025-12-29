#!/usr/bin/env python3
"""
METATRON - One-Click Deploy System for Time Testnet

The angel who governs the Pantheon of gods.
Analyzes, deploys, and monitors all 12 modules.

Usage:
    python metatron.py              # Status check
    python metatron.py --deploy     # Deploy testnet node
    python metatron.py --dashboard  # Live dashboard
"""

import os
import sys
import time
import threading
import argparse
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

# ============================================================================
# CONFIGURATION
# ============================================================================

class GodStatus(Enum):
    """Status of a Pantheon god."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    ERROR = "ERROR"
    STUB = "STUB"


@dataclass
class God:
    """Pantheon god definition."""
    name: str
    symbol: str
    domain: str
    modules: List[str]
    status: GodStatus = GodStatus.OFFLINE
    error: Optional[str] = None
    metrics: Dict = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}


# The 12 Gods of Pantheon
PANTHEON = {
    "chronos": God(
        name="Chronos",
        symbol="⏱",
        domain="Time (VDF, PoH)",
        modules=["pantheon.chronos.poh", "pantheon.chronos.vdf_fast"]
    ),
    "adonis": God(
        name="Adonis",
        symbol="✋",
        domain="Reputation (5 Fingers)",
        modules=["pantheon.adonis.adonis"]
    ),
    "hermes": God(
        name="Hermes",
        symbol="📡",
        domain="P2P Network",
        modules=["pantheon.hermes.network", "pantheon.hermes.bootstrap"]
    ),
    "hades": God(
        name="Hades",
        symbol="💾",
        domain="Storage (DAG, DB)",
        modules=["pantheon.hades.database", "pantheon.hades.dag", "pantheon.hades.dag_storage"]
    ),
    "athena": God(
        name="Athena",
        symbol="⚖",
        domain="Consensus (VRF)",
        modules=["pantheon.athena.consensus", "pantheon.athena.engine"]
    ),
    "prometheus": God(
        name="Prometheus",
        symbol="🔐",
        domain="Cryptography",
        modules=["pantheon.prometheus.crypto"]
    ),
    "mnemosyne": God(
        name="Mnemosyne",
        symbol="📋",
        domain="Mempool",
        modules=[]  # Stub
    ),
    "plutus": God(
        name="Plutus",
        symbol="💰",
        domain="Wallet (UTXO)",
        modules=["pantheon.plutus.wallet"]
    ),
    "nyx": God(
        name="Nyx",
        symbol="🌙",
        domain="Privacy (Ring, Stealth)",
        modules=["pantheon.nyx.privacy", "pantheon.nyx.tiered_privacy", "pantheon.nyx.ristretto"]
    ),
    "themis": God(
        name="Themis",
        symbol="📜",
        domain="Validation",
        modules=["pantheon.themis.structures"]
    ),
    "iris": God(
        name="Iris",
        symbol="🌈",
        domain="RPC & Dashboard",
        modules=["pantheon.iris.rpc"]
    ),
    "ananke": God(
        name="Ananke",
        symbol="🏛",
        domain="Governance",
        modules=[]  # Stub
    ),
}


# ============================================================================
# METATRON CORE
# ============================================================================

class Metatron:
    """
    The angel who governs the Pantheon.

    Metatron is the scribe of God in Jewish tradition,
    responsible for recording all events in the universe.
    Here, he orchestrates the 12 gods of Proof of Time.
    """

    def __init__(self):
        self.gods = PANTHEON.copy()
        self.node = None
        self.running = False
        self._lock = threading.Lock()

    def analyze(self) -> Dict[str, GodStatus]:
        """Analyze all gods and return their status."""
        results = {}

        for god_id, god in self.gods.items():
            if not god.modules:
                god.status = GodStatus.STUB
                results[god_id] = GodStatus.STUB
                continue

            try:
                for module in god.modules:
                    __import__(module)
                god.status = GodStatus.OFFLINE  # Importable but not running
                results[god_id] = GodStatus.OFFLINE
            except Exception as e:
                god.status = GodStatus.ERROR
                god.error = str(e)
                results[god_id] = GodStatus.ERROR

        return results

    def deploy(self, peer_address: Optional[str] = None) -> bool:
        """Deploy a testnet node with all gods active."""
        print("\n" + "="*60)
        print("  METATRON - Deploying Time Testnet Node")
        print("="*60 + "\n")

        # Set environment
        os.environ.setdefault("POT_NETWORK", "TESTNET")
        os.environ.setdefault("POT_ALLOW_UNSAFE", "1")

        if peer_address:
            os.environ["POT_BOOTSTRAP_PEERS"] = peer_address
            print(f"  Bootstrap peer: {peer_address}")

        # Analyze gods
        print("\n  Analyzing Pantheon...")
        results = self.analyze()

        ready = sum(1 for s in results.values() if s != GodStatus.ERROR)
        total = len(results)

        print(f"  Gods ready: {ready}/{total}")

        if ready < 10:
            print("\n  ERROR: Too many gods in ERROR state. Cannot deploy.")
            return False

        # Start node
        print("\n  Starting node...")
        try:
            from node import FullNode, BlockProducer
            from config import NodeConfig

            config = NodeConfig()
            self.node = FullNode(config)
            self.node.start()

            # Mark gods as online
            for god_id in self.gods:
                if self.gods[god_id].status != GodStatus.STUB:
                    self.gods[god_id].status = GodStatus.ONLINE

            print("  Node started successfully!")
            self.running = True
            return True

        except Exception as e:
            print(f"  ERROR: Failed to start node: {e}")
            return False

    def stop(self):
        """Stop the node."""
        if self.node:
            self.node.stop()
            self.running = False
            for god in self.gods.values():
                if god.status == GodStatus.ONLINE:
                    god.status = GodStatus.OFFLINE

    def get_status_display(self) -> str:
        """Get visual status of all gods."""
        lines = []
        lines.append("")
        lines.append("╔════════════════════════════════════════════════════════════╗")
        lines.append("║              PANTHEON - The 12 Gods of Time                ║")
        lines.append("╠════════════════════════════════════════════════════════════╣")

        for god_id, god in self.gods.items():
            status_color = {
                GodStatus.ONLINE: "\033[92m●\033[0m",   # Green
                GodStatus.OFFLINE: "\033[90m○\033[0m",  # Gray
                GodStatus.STARTING: "\033[93m◐\033[0m", # Yellow
                GodStatus.ERROR: "\033[91m✗\033[0m",    # Red
                GodStatus.STUB: "\033[90m◌\033[0m",     # Gray hollow
            }.get(god.status, "?")

            status_text = god.status.value.ljust(8)
            name = f"{god.symbol} {god.name}".ljust(15)
            domain = god.domain[:25].ljust(25)

            lines.append(f"║  {status_color} {name} │ {domain} │ {status_text} ║")

        lines.append("╠════════════════════════════════════════════════════════════╣")

        # Summary
        online = sum(1 for g in self.gods.values() if g.status == GodStatus.ONLINE)
        total = len(self.gods)
        stubs = sum(1 for g in self.gods.values() if g.status == GodStatus.STUB)

        summary = f"Online: {online}/{total-stubs} active gods, {stubs} stubs"
        lines.append(f"║  {summary.center(56)} ║")
        lines.append("╚════════════════════════════════════════════════════════════╝")
        lines.append("")

        return "\n".join(lines)

    def dashboard(self, refresh_rate: float = 1.0):
        """Run live dashboard."""
        print("\033[2J\033[H")  # Clear screen
        print("METATRON Dashboard - Press Ctrl+C to exit\n")

        try:
            while True:
                # Update metrics if node is running
                if self.node and self.running:
                    self._update_metrics()

                # Clear and redraw
                print("\033[H")  # Move cursor to top
                print(self.get_status_display())

                # Show node metrics if available
                if self.node and self.running:
                    self._print_node_metrics()

                time.sleep(refresh_rate)

        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.stop()

    def _update_metrics(self):
        """Update god metrics from running node."""
        if not self.node:
            return

        try:
            # Chronos - block height
            if self.node.chain_tip:
                self.gods["chronos"].metrics["height"] = self.node.chain_tip.height

            # Hermes - peer count
            if hasattr(self.node.network, 'peers'):
                self.gods["hermes"].metrics["peers"] = len(self.node.network.peers)

            # Hades - blocks stored
            self.gods["hades"].metrics["blocks"] = self.node.chain_tip.height + 1 if self.node.chain_tip else 0

            # Athena - nodes registered
            if hasattr(self.node.consensus, 'nodes'):
                self.gods["athena"].metrics["nodes"] = len(self.node.consensus.nodes)

        except Exception:
            pass

    def _print_node_metrics(self):
        """Print node metrics."""
        print("\n┌─────────────────────────────────────────────────────────────┐")
        print("│                      NODE METRICS                           │")
        print("├─────────────────────────────────────────────────────────────┤")

        height = self.gods["chronos"].metrics.get("height", 0)
        peers = self.gods["hermes"].metrics.get("peers", 0)
        nodes = self.gods["athena"].metrics.get("nodes", 0)

        print(f"│  Height: {str(height).ljust(10)} Peers: {str(peers).ljust(5)} Consensus Nodes: {nodes}   │")
        print("└─────────────────────────────────────────────────────────────┘")


# ============================================================================
# CLI
# ============================================================================

def print_banner():
    """Print Metatron banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███╗   ███╗███████╗████████╗ █████╗ ████████╗██████╗  ██████╗ ███╗   ██╗ ║
    ║   ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗╚══██╔══╝██╔══██╗██╔═══██╗████╗  ██║ ║
    ║   ██╔████╔██║█████╗     ██║   ███████║   ██║   ██████╔╝██║   ██║██╔██╗ ██║ ║
    ║   ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║   ██║   ██╔══██╗██║   ██║██║╚██╗██║ ║
    ║   ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║   ██║   ██║  ██║╚██████╔╝██║ ╚████║ ║
    ║   ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ║
    ║                                                               ║
    ║              The Angel Who Governs the Pantheon               ║
    ║                   Time Testnet Deployer                       ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="METATRON - One-Click Deploy System for Time Testnet"
    )
    parser.add_argument(
        "--deploy", "-d",
        action="store_true",
        help="Deploy a testnet node"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run live dashboard"
    )
    parser.add_argument(
        "--peer", "-p",
        type=str,
        default=None,
        help="Bootstrap peer address (ip:port)"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show Pantheon status"
    )

    args = parser.parse_args()

    print_banner()

    metatron = Metatron()

    if args.status or (not args.deploy and not args.dashboard):
        # Default: show status
        metatron.analyze()
        print(metatron.get_status_display())

        # Show summary
        errors = [g for g in metatron.gods.values() if g.status == GodStatus.ERROR]
        if errors:
            print("\nErrors detected:")
            for god in errors:
                print(f"  - {god.name}: {god.error}")
        else:
            print("\nAll gods ready for deployment.")
            print("Run: python metatron.py --deploy")

    elif args.deploy:
        if metatron.deploy(args.peer):
            print("\n" + "="*60)
            print("  Node deployed successfully!")
            print("="*60)
            print("\nRun dashboard: python metatron.py --dashboard")
            print("Or press Ctrl+C to stop the node.\n")

            # Keep running
            try:
                while metatron.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping node...")
                metatron.stop()
        else:
            sys.exit(1)

    elif args.dashboard:
        metatron.analyze()
        metatron.dashboard()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    main()
