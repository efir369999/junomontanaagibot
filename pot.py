#!/usr/bin/env python3
"""
Proof of Time - Unified Node + Dashboard

Simple log-style output showing all protocol parameters.

Usage:
    python pot.py              # Run node with dashboard
    python pot.py --demo       # Demo mode with sample data
    python pot.py --web 8080   # Also start web dashboard on port 8080
"""

import os
import sys
import time
import signal
import threading
import argparse
import logging
from datetime import datetime

# ============================================================================
# PANTHEON GODS DATA
# ============================================================================

GODS = {
    "Chronos": {
        "domain": "Time/VDF",
        "status": "ACTIVE",
        "module": "crypto.py",
        "functions": ["compute_vdf", "verify_vdf", "get_checkpoint"],
        "params": {"T": 1000000, "checkpoint_interval": 600, "difficulty": "2^20"}
    },
    "Adonis": {
        "domain": "Reputation",
        "status": "ACTIVE",
        "module": "adonis.py",
        "functions": ["record_event", "get_score", "compute_pagerank"],
        "params": {"dimensions": 6, "decay_rate": 0.99, "max_vouches_day": 10}
    },
    "Hermes": {
        "domain": "Network/P2P",
        "status": "ACTIVE",
        "module": "network.py",
        "functions": ["connect", "broadcast", "sync"],
        "params": {"protocol": "Noise_XX", "max_peers": 50, "port": 9333}
    },
    "Hades": {
        "domain": "Storage",
        "status": "ACTIVE",
        "module": "database.py",
        "functions": ["store_block", "get_block", "prune"],
        "params": {"backend": "SQLite", "dag_enabled": True, "max_size_gb": 100}
    },
    "Athena": {
        "domain": "Consensus",
        "status": "ACTIVE",
        "module": "consensus.py",
        "functions": ["select_leader", "validate_block", "finalize"],
        "params": {"vrf_threshold": "dynamic", "finality_depth": 6, "epoch_slots": 600}
    },
    "Prometheus": {
        "domain": "Cryptography",
        "status": "ACTIVE",
        "module": "crypto.py",
        "functions": ["sign", "verify", "vrf_prove"],
        "params": {"curve": "Ed25519", "vrf": "ECVRF", "hash": "SHA256"}
    },
    "Mnemosyne": {
        "domain": "Memory/Cache",
        "status": "ACTIVE",
        "module": "structures.py",
        "functions": ["add_tx", "get_pending", "clear"],
        "params": {"mempool_max": 10000, "cache_ttl": 300, "gc_interval": 60}
    },
    "Plutus": {
        "domain": "Wallet",
        "status": "ACTIVE",
        "module": "wallet.py",
        "functions": ["create_wallet", "sign_tx", "get_balance"],
        "params": {"key_derivation": "Ed25519", "address_prefix": "pot1", "dust_limit": 1000}
    },
    "Nyx": {
        "domain": "Privacy",
        "status": "LIMITED",
        "module": "privacy.py",
        "functions": ["stealth_address", "ring_sign", "bulletproof"],
        "params": {"ring_size": 11, "stealth": True, "confidential": "disabled"}
    },
    "Themis": {
        "domain": "Validation",
        "status": "ACTIVE",
        "module": "node.py",
        "functions": ["validate_tx", "validate_block", "check_rules"],
        "params": {"max_block_size": 1048576, "max_tx_size": 100000, "sig_ops_limit": 20000}
    },
    "Iris": {
        "domain": "API/RPC",
        "status": "ACTIVE",
        "module": "node.py",
        "functions": ["getinfo", "sendtx", "getblock"],
        "params": {"rpc_port": 8332, "ws_port": 8333, "cors": True}
    },
    "Ananke": {
        "domain": "Governance",
        "status": "PLANNED",
        "module": "-",
        "functions": ["propose", "vote", "execute"],
        "params": {"voting_period": 604800, "quorum": 0.1, "threshold": 0.67}
    },
}

# ============================================================================
# SIMPLE LOG-STYLE DASHBOARD
# ============================================================================

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')

def print_header():
    print()
    print("=" * 70)
    print("PROOF OF TIME - PANTHEON PROTOCOL v2.2")
    print("\"Chronos proves, Athena selects, Adonis trusts.\"")
    print("=" * 70)
    print()

def print_gods():
    print("[PANTHEON] The 12 Gods of Protocol")
    print("-" * 70)

    for i, (name, data) in enumerate(GODS.items(), 1):
        status = data["status"]
        print(f"  [{i:2}] {name}")
        print(f"       Domain:    {data['domain']}")
        print(f"       Status:    {status}")
        print(f"       Module:    {data['module']}")
        print(f"       Functions: {', '.join(data['functions'])}")
        print(f"       Params:    ", end="")
        params = [f"{k}={v}" for k, v in data['params'].items()]
        print(", ".join(params))
        print()

def print_adonis(engine):
    print("[ADONIS] Reputation Engine Status")
    print("-" * 70)

    if engine:
        stats = engine.get_stats()
        print(f"  Total Nodes:     {stats['total_profiles']}")
        print(f"  Active Nodes:    {stats['active_profiles']}")
        print(f"  Penalized:       {stats['penalized_profiles']}")
        print(f"  Total Vouches:   {stats['total_vouches']}")
        print(f"  Average Score:   {stats['average_score']:.4f}")
        print(f"  Unique Cities:   {stats['unique_cities']}")
        print()
        print("  Dimension Weights:")
        for dim, weight in stats['dimension_weights'].items():
            pct = int(weight * 100)
            bar = "#" * (pct // 2) + "." * (50 - pct // 2)
            print(f"    {dim:12} [{bar}] {pct}%")
    else:
        print("  No data available")
    print()

def print_geography(engine):
    print("[GEOGRAPHY] Network Distribution")
    print("-" * 70)

    if engine:
        diversity = engine.get_geographic_diversity_score()
        cities = engine.get_city_distribution()

        print(f"  Unique Cities:   {len(cities)}")
        print(f"  Diversity Score: {diversity*100:.1f}%")
        print()

        if cities:
            print("  City Distribution (hash prefix -> count):")
            sorted_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)
            for hash_prefix, count in sorted_cities[:10]:
                bar = "#" * min(count * 2, 40)
                print(f"    {hash_prefix}: {bar} ({count})")
    else:
        print("  No data available")
    print()

def print_nodes(engine):
    print("[NODES] Top Nodes by Reputation")
    print("-" * 70)

    if engine:
        top = engine.get_top_nodes(15)

        print(f"  {'#':3} {'Node ID':20} {'Score':8} {'City':10} {'Vouches':8}")
        print(f"  {'-'*60}")

        for i, (pubkey, score) in enumerate(top, 1):
            profile = engine.get_profile(pubkey)
            city = profile.city_hash.hex()[:8] if profile and profile.city_hash else "--------"
            vouches = len(profile.trusted_by) if profile else 0
            print(f"  {i:3} {pubkey.hex()[:18]}.. {score:.4f}   {city}   {vouches:3}")
    else:
        print("  No data available")
    print()

def print_events(engine):
    print("[EVENTS] Recent Activity")
    print("-" * 70)

    if engine:
        events = []
        for pubkey, profile in engine.profiles.items():
            for e in profile.history[-5:]:
                events.append((e.timestamp, pubkey, e.event_type.name, e.impact))

        events.sort(key=lambda x: x[0], reverse=True)

        print(f"  {'Time':10} {'Node':14} {'Event':18} {'Impact':8}")
        print(f"  {'-'*55}")

        for ts, pk, event, impact in events[:15]:
            time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            impact_str = f"+{impact:.2f}" if impact >= 0 else f"{impact:.2f}"
            print(f"  {time_str}   {pk.hex()[:12]}..   {event:18} {impact_str}")
    else:
        print("  No data available")
    print()

def print_footer():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("-" * 70)
    print(f"Updated: {now}")
    print("Controls: [1] Gods  [2] Adonis  [3] Geo  [4] Nodes  [5] Events  [q] Quit")
    print()

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

class Dashboard:
    def __init__(self, engine=None, demo=False):
        self.engine = engine
        self.demo = demo
        self.running = True
        self.current_view = 0  # 0=gods, 1=adonis, 2=geo, 3=nodes, 4=events

    def render(self):
        clear_screen()
        print_header()

        if self.current_view == 0:
            print_gods()
        elif self.current_view == 1:
            print_adonis(self.engine)
        elif self.current_view == 2:
            print_geography(self.engine)
        elif self.current_view == 3:
            print_nodes(self.engine)
        elif self.current_view == 4:
            print_events(self.engine)

        print_footer()

    def handle_input(self):
        import select
        import tty
        import termios

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())

            while self.running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch = sys.stdin.read(1)

                    if ch == 'q' or ch == 'Q':
                        self.running = False
                    elif ch == 'r' or ch == 'R':
                        self.render()
                    elif ch in '12345':
                        self.current_view = int(ch) - 1
                        self.render()
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def run(self):
        self.render()

        input_thread = threading.Thread(target=self.handle_input, daemon=True)
        input_thread.start()

        while self.running:
            time.sleep(5)
            if self.running:
                self.render()


# ============================================================================
# DEMO DATA
# ============================================================================

def generate_demo_data(engine):
    import random
    from adonis import ReputationEvent

    cities = [
        ("US", "New York"), ("US", "Los Angeles"), ("JP", "Tokyo"),
        ("DE", "Berlin"), ("GB", "London"), ("FR", "Paris"),
        ("SG", "Singapore"), ("AU", "Sydney"), ("KR", "Seoul"),
        ("CA", "Toronto"), ("NL", "Amsterdam"), ("BR", "Sao Paulo")
    ]

    for i in range(20):
        pk = bytes([i + 1] * 32)
        country, city = random.choice(cities)
        engine.register_node_location(pk, country, city)

        for _ in range(random.randint(10, 40)):
            evt = random.choice([
                ReputationEvent.BLOCK_PRODUCED,
                ReputationEvent.BLOCK_VALIDATED,
                ReputationEvent.TX_RELAYED,
                ReputationEvent.UPTIME_CHECKPOINT
            ]) if random.random() > 0.1 else ReputationEvent.DOWNTIME
            engine.record_event(pk, evt, height=random.randint(1, 10000))

        if i > 0 and random.random() > 0.6:
            voucher = bytes([random.randint(1, i)] * 32)
            engine.add_vouch(voucher, pk)


# ============================================================================
# WEB SERVER
# ============================================================================

def start_web_server(engine, port):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/api/overview':
                stats = engine.get_stats()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(stats).encode())
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Pantheon</h1><p>/api/overview</p>")

    def run_server():
        HTTPServer(('0.0.0.0', port), Handler).serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Proof of Time Node + Dashboard")
    parser.add_argument("--demo", action="store_true", help="Demo mode")
    parser.add_argument("--web", type=int, metavar="PORT", help="Web dashboard port")
    parser.add_argument("--no-tui", action="store_true", help="No terminal UI")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    from adonis import AdonisEngine
    engine = AdonisEngine()

    if args.demo:
        generate_demo_data(engine)

    if args.web:
        start_web_server(engine, args.web)
        print(f"Web: http://0.0.0.0:{args.web}")

    if not args.no_tui:
        dashboard = Dashboard(engine=engine, demo=args.demo)

        def signal_handler(sig, frame):
            dashboard.running = False
            print("\nShutting down...")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        try:
            dashboard.run()
        except KeyboardInterrupt:
            pass
        finally:
            print("\nGoodbye!\n")
    else:
        print("Node running... Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == "__main__":
    main()
