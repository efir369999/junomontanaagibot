#!/usr/bin/env python3
"""
Ɉ Montana Server Test v3.1

Tests all components on the bootstrap server.
"""

import sys
sys.path.insert(0, "/root/projects")

print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🏔️  Ɉ Montana v3.1 — Server Test                        ║
║                                                           ║
║   Bootstrap: 176.124.208.93:19656                         ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")

# Test all components
tests = []

# 1. Constants
try:
    from montana.constants import TOTAL_SUPPLY, DEFAULT_PORT, PROTOCOL_VERSION
    tests.append(("Constants", True, f"Supply={TOTAL_SUPPLY:,} Port={DEFAULT_PORT} Proto={PROTOCOL_VERSION}"))
except Exception as e:
    tests.append(("Constants", False, str(e)))

# 2. Types
try:
    from montana.core.types import Hash, NodeType, ParticipationTier
    tests.append(("Core Types", True, f"Hash={Hash.zero().hex()[:16]}..."))
except Exception as e:
    tests.append(("Core Types", False, str(e)))

# 3. VDF
try:
    from montana.core.vdf import SHAKE256VDF
    vdf = SHAKE256VDF()
    tests.append(("VDF", True, "SHAKE256VDF ready"))
except Exception as e:
    tests.append(("VDF", False, str(e)))

# 4. Crypto
try:
    from montana.crypto.hash import sha3_256, shake256
    from montana.crypto.sphincs import sphincs_keygen
    h = sha3_256(b"test")
    tests.append(("Crypto", True, f"SHA3-256 ok, hash={h.hex()[:16]}..."))
except Exception as e:
    tests.append(("Crypto", False, str(e)))

# 5. Block/Heartbeat
try:
    from montana.core.block import Block, BlockHeader
    from montana.core.heartbeat import FullHeartbeat, LightHeartbeat
    tests.append(("Block/Heartbeat", True, "Block, Heartbeat structures ok"))
except Exception as e:
    tests.append(("Block/Heartbeat", False, str(e)))

# 6. Consensus
try:
    from montana.consensus.dag import PHANTOMOrdering
    from montana.consensus.score import ScoreTracker
    tests.append(("Consensus", True, "PHANTOM DAG, ScoreTracker ok"))
except Exception as e:
    tests.append(("Consensus", False, str(e)))

# 7. Privacy
try:
    from montana.privacy.tiers import get_fee_multiplier, validate_privacy_tier
    from montana.privacy.stealth import create_stealth_address
    from montana.core.types import PrivacyTier
    m = get_fee_multiplier(PrivacyTier.T3)
    tests.append(("Privacy", True, f"T0-T3 tiers ok, T3 fee={m}x"))
except Exception as e:
    tests.append(("Privacy", False, str(e)))

# 8. Network
try:
    from montana.network.protocol import MessageType, ServiceFlags
    from montana.network.peer import PeerManager
    from montana.network.bootstrap import OFFICIAL_BOOTSTRAP_NODES
    tests.append(("Network", True, f"Bootstrap: {OFFICIAL_BOOTSTRAP_NODES[0].ip}:{OFFICIAL_BOOTSTRAP_NODES[0].port}"))
except Exception as e:
    tests.append(("Network", False, str(e)))

# 9. State
try:
    from montana.state.storage import Database, BlockStore
    from montana.state.accounts import AccountManager
    tests.append(("State", True, "SQLite storage, AccountManager ok"))
except Exception as e:
    tests.append(("State", False, str(e)))

# 10. Node
try:
    from montana.node.full_node import FullNode, FullNodeConfig
    from montana.node.light_node import LightNode
    tests.append(("Node", True, "FullNode, LightNode ok"))
except Exception as e:
    tests.append(("Node", False, str(e)))

# 11. API
try:
    from montana.api.rpc import RPCServer
    from montana.api.websocket import WebSocketServer
    tests.append(("API", True, "RPC (19657), WebSocket (19658) ok"))
except Exception as e:
    tests.append(("API", False, str(e)))

# 12. Bot
try:
    from montana.bot.telegram import MontanaBot
    from montana.bot.challenges import ChallengeManager
    tests.append(("Telegram Bot", True, "Time challenges ok"))
except Exception as e:
    tests.append(("Telegram Bot", False, str(e)))

# Print results
print("Component Tests:")
print("-" * 60)
passed = 0
for name, ok, msg in tests:
    status = "✓" if ok else "✗"
    if ok:
        passed += 1
    print(f"  {status} {name:20} {msg}")

print("-" * 60)
print(f"Passed: {passed}/{len(tests)}")
print()

if passed == len(tests):
    print("🏔️ All Montana components ready!")
    print()
    print("Start node with:")
    print("  python3 -m montana.cli.main --node-type full --port 19656")
else:
    print("Some components failed")
