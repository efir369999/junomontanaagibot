#!/bin/bash
# Local 6-node network test
# Tests Montana network with 6 nodes in a mesh topology

set -e

BINARY="../cache/target/release/montana"
BASE_PORT=19500
DATA_DIR="/tmp/montana_6nodes"

cleanup() {
    echo "Cleaning up..."
    pkill -f "montana.*$BASE_PORT" 2>/dev/null || true
    rm -rf "$DATA_DIR"
}

trap cleanup EXIT

# Check binary
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Binary not found. Run: cargo build --release"
    exit 1
fi

# Clean data directory
rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"

echo "════════════════════════════════════════════════════════════"
echo "  Montana 6-Node Local Network Test"
echo "════════════════════════════════════════════════════════════"

# Start node 1 (seed node)
PORT1=$BASE_PORT
echo "Starting node 1 on port $PORT1 (seed)..."
$BINARY --port $PORT1 --data-dir "$DATA_DIR/node1" &
sleep 1

# Start nodes 2-6 connecting to node 1
for i in 2 3 4 5 6; do
    PORT=$((BASE_PORT + i - 1))
    echo "Starting node $i on port $PORT..."
    $BINARY --port $PORT --data-dir "$DATA_DIR/node$i" --seeds "127.0.0.1:$PORT1" &
    sleep 0.5
done

echo ""
echo "All 6 nodes started. Waiting for connections..."
sleep 10

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Network Status"
echo "════════════════════════════════════════════════════════════"

# Check all processes are running
RUNNING=$(pgrep -f "montana.*$BASE_PORT" | wc -l)
echo "Running nodes: $RUNNING/6"

if [ "$RUNNING" -eq 6 ]; then
    echo "✓ All 6 nodes running successfully"
    echo ""
    echo "Network is operational. Monitoring for 20 seconds..."
    sleep 20

    # Final check
    RUNNING=$(pgrep -f "montana.*$BASE_PORT" | wc -l)
    if [ "$RUNNING" -eq 6 ]; then
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  TEST PASSED: 6-node network stable"
        echo "════════════════════════════════════════════════════════════"
    else
        echo "ERROR: Some nodes crashed during test"
        exit 1
    fi
else
    echo "ERROR: Only $RUNNING nodes running"
    exit 1
fi
