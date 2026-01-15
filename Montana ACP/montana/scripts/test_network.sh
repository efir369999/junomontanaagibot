#!/bin/bash
# Montana Network Test Script
# Tests connection between local and remote node

set -e

SERVER_IP="176.124.208.93"
SERVER_PORT="9000"
LOCAL_PORT="19500"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() { echo -e "${GREEN}✓${NC} $1"; }
log_fail() { echo -e "${RED}✗${NC} $1"; }
log_info() { echo -e "${YELLOW}→${NC} $1"; }

echo "════════════════════════════════════════════════════"
echo "  Montana Network Test"
echo "════════════════════════════════════════════════════"
echo ""

# Test 1: Server reachability
log_info "Test 1: Checking server reachability..."
if nc -z -w5 $SERVER_IP $SERVER_PORT 2>/dev/null; then
    log_ok "Server $SERVER_IP:$SERVER_PORT is reachable"
else
    log_fail "Server $SERVER_IP:$SERVER_PORT is NOT reachable"
    echo "    Make sure server is running: ./montana --port $SERVER_PORT"
    exit 1
fi

# Test 2: Start local node and check connection
log_info "Test 2: Starting local node..."

BINARY="./target/release/montana"
if [ ! -f "$BINARY" ]; then
    log_fail "Binary not found. Run: cargo build --release"
    exit 1
fi

DATA_DIR="/tmp/montana_test_local"
rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"

# Start node in background, capture output
RUST_LOG=montana=info $BINARY \
    --port $LOCAL_PORT \
    --data-dir "$DATA_DIR" \
    --seeds "$SERVER_IP:$SERVER_PORT" \
    2>&1 | tee /tmp/montana_test.log &

NODE_PID=$!
echo "    Local node PID: $NODE_PID"

# Wait for connection
sleep 5

# Check if connected
if grep -q "Peer connected" /tmp/montana_test.log; then
    log_ok "Peer connection established"
else
    log_fail "No peer connection in logs"
    kill $NODE_PID 2>/dev/null || true
    exit 1
fi

# Test 3: Check peer count
log_info "Test 3: Checking peer count..."
sleep 2

if grep -q "1 peers" /tmp/montana_test.log; then
    log_ok "Peer count = 1"
else
    log_fail "Unexpected peer count"
fi

# Test 4: Let it run for 30 seconds, check stability
log_info "Test 4: Stability check (30 seconds)..."
sleep 30

if ps -p $NODE_PID > /dev/null 2>&1; then
    log_ok "Node still running after 30s"
else
    log_fail "Node crashed"
    exit 1
fi

# Check last status
LAST_STATUS=$(grep "Status:" /tmp/montana_test.log | tail -1)
echo "    $LAST_STATUS"

# Cleanup
kill $NODE_PID 2>/dev/null || true
rm -rf "$DATA_DIR"

echo ""
echo "════════════════════════════════════════════════════"
log_ok "All network tests passed!"
echo "════════════════════════════════════════════════════"
