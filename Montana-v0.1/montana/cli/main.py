"""
Ɉ Montana CLI v3.1

Command-line interface for running Montana nodes.

Usage:
    python -m montana.cli.main --node-type full --bootstrap 176.124.208.93:19656
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from montana.constants import DEFAULT_PORT, PROTOCOL_VERSION


# Configure logging
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ɉ Montana Node v3.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full node with default settings
  python -m montana.cli.main --node-type full

  # Run full node with custom bootstrap
  python -m montana.cli.main --node-type full --bootstrap 176.124.208.93:19656

  # Run light node
  python -m montana.cli.main --node-type light

  # Generate new keys
  python -m montana.cli.main --generate-keys

For more information, visit: https://montana.network
        """
    )

    # Node type
    parser.add_argument(
        "--node-type",
        choices=["full", "light"],
        default="full",
        help="Type of node to run (default: full)",
    )

    # Network
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--bootstrap",
        action="append",
        default=[],
        help="Bootstrap node address (ip:port)",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Don't connect to bootstrap nodes",
    )

    # Data
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./montana_data",
        help="Data directory (default: ./montana_data)",
    )

    # Keys
    parser.add_argument(
        "--keyfile",
        type=str,
        default=None,
        help="Path to key file",
    )
    parser.add_argument(
        "--generate-keys",
        action="store_true",
        help="Generate new keypair and exit",
    )

    # Mining
    parser.add_argument(
        "--no-mining",
        action="store_true",
        help="Disable block production",
    )

    # API
    parser.add_argument(
        "--rpc-host",
        type=str,
        default="127.0.0.1",
        help="RPC server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--rpc-port",
        type=int,
        default=19657,
        help="RPC server port (default: 19657)",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=19658,
        help="WebSocket server port (default: 19658)",
    )
    parser.add_argument(
        "--no-rpc",
        action="store_true",
        help="Disable RPC server",
    )
    parser.add_argument(
        "--no-ws",
        action="store_true",
        help="Disable WebSocket server",
    )

    # Misc
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Montana v{PROTOCOL_VERSION}",
    )

    return parser.parse_args()


def generate_keys(keyfile: str = None):
    """Generate new keypair."""
    from montana.crypto.sphincs import generate_sphincs_keypair
    import json

    print("Generating SPHINCS+ keypair...")

    pk, sk = generate_sphincs_keypair()

    key_data = {
        "public_key": pk.serialize().hex(),
        "secret_key": sk.serialize().hex(),
    }

    if keyfile:
        path = Path(keyfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(key_data, f, indent=2)
        print(f"Keys saved to: {keyfile}")
    else:
        print(f"Public key: {pk.serialize().hex()[:64]}...")
        print(f"Secret key: {sk.serialize().hex()[:64]}...")
        print("\nUse --keyfile to save keys to a file")

    # Show node ID
    from montana.core.types import Hash
    node_id = Hash(pk.serialize()[:32])
    print(f"\nNode ID: {node_id.hex()}")


def load_keys(keyfile: str):
    """Load keypair from file."""
    import json
    from montana.core.types import PublicKey, SecretKey

    with open(keyfile) as f:
        data = json.load(f)

    pk = PublicKey.deserialize(bytes.fromhex(data["public_key"]), 0)[0]
    sk = SecretKey.deserialize(bytes.fromhex(data["secret_key"]), 0)[0]

    return pk, sk


async def run_full_node(args: argparse.Namespace, pk, sk):
    """Run a full node."""
    from montana.node.full_node import FullNode, FullNodeConfig
    from montana.api.rpc import RPCServer, create_node_rpc
    from montana.api.websocket import WebSocketServer, create_node_websocket

    # Create config
    config = FullNodeConfig(
        data_dir=args.data_dir,
        port=args.port,
        bootstrap=args.bootstrap,
        enable_mining=not args.no_mining,
    )

    # Create node
    node = FullNode(config, sk, pk)

    # Create API servers
    rpc_server = None
    ws_server = None

    if not args.no_rpc:
        rpc_server = create_node_rpc(node)
        rpc_server.host = args.rpc_host
        rpc_server.port = args.rpc_port

    if not args.no_ws:
        ws_server = WebSocketServer(host=args.rpc_host, port=args.ws_port)

    # Signal handler
    stop_event = asyncio.Event()

    def signal_handler():
        print("\nShutting down...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start services
    try:
        await node.start()

        if rpc_server:
            await rpc_server.start()

        if ws_server:
            await ws_server.start()
            create_node_websocket(node, ws_server)

        print(f"\n🏔️ Montana Full Node running")
        print(f"   Node ID: {node.node_id.hex()[:16]}...")
        print(f"   Port: {args.port}")
        if rpc_server:
            print(f"   RPC: http://{args.rpc_host}:{args.rpc_port}")
        if ws_server:
            print(f"   WS: ws://{args.rpc_host}:{args.ws_port}/ws")
        print()

        # Wait for shutdown
        await stop_event.wait()

    finally:
        if ws_server:
            await ws_server.stop()
        if rpc_server:
            await rpc_server.stop()
        await node.stop()


async def run_light_node(args: argparse.Namespace, pk, sk):
    """Run a light node."""
    from montana.node.light_node import LightNode, LightNodeConfig

    config = LightNodeConfig(
        port=0,  # Light nodes don't listen
        bootstrap=args.bootstrap,
    )

    node = LightNode(config, sk, pk)

    # Signal handler
    stop_event = asyncio.Event()

    def signal_handler():
        print("\nShutting down...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await node.start()

        print(f"\n🏔️ Montana Light Node running")
        print(f"   Node ID: {node.node_id.hex()[:16]}...")
        print()

        await stop_event.wait()

    finally:
        await node.stop()


def main():
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🏔️  Ɉ Montana v{PROTOCOL_VERSION}                                   ║
    ║                                                           ║
    ║   Mechanism for Asymptotic Trust in Time Value            ║
    ║   lim(evidence → ∞) 1 Ɉ → 1 second                        ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    # Generate keys mode
    if args.generate_keys:
        generate_keys(args.keyfile)
        return

    # Load or generate keys
    if args.keyfile and os.path.exists(args.keyfile):
        print(f"Loading keys from {args.keyfile}...")
        pk, sk = load_keys(args.keyfile)
    else:
        print("Generating ephemeral keypair...")
        from montana.crypto.sphincs import sphincs_keygen
        keypair = sphincs_keygen()
        pk, sk = keypair.public, keypair.secret
        if not args.keyfile:
            print("Warning: Using ephemeral keys. Use --keyfile to persist.")

    # Create data directory
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    # Add default bootstrap if none specified
    if not args.bootstrap and not args.no_bootstrap:
        args.bootstrap = ["176.124.208.93:19656"]

    # Run node
    if args.node_type == "full":
        asyncio.run(run_full_node(args, pk, sk))
    else:
        asyncio.run(run_light_node(args, pk, sk))


if __name__ == "__main__":
    main()
