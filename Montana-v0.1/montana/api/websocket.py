"""
Ɉ Montana WebSocket Server v3.1

WebSocket API for real-time events per MONTANA_TECHNICAL_SPECIFICATION.md §20.2.
"""

from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import IntEnum, auto
import weakref

from aiohttp import web, WSMsgType

from montana.constants import WS_PORT
from montana.core.types import Hash

logger = logging.getLogger(__name__)


class WSEvent(IntEnum):
    """WebSocket event types."""
    NEW_BLOCK = 1
    NEW_TRANSACTION = 2
    NEW_HEARTBEAT = 3
    PEER_CONNECTED = 4
    PEER_DISCONNECTED = 5
    SYNC_STATUS = 6
    VDF_CHECKPOINT = 7
    FINALITY_UPDATE = 8


@dataclass
class Subscription:
    """Client subscription."""
    event_type: WSEvent
    filter: Optional[Dict] = None


class WebSocketServer:
    """
    WebSocket server for real-time events.

    Provides:
    - New block notifications
    - Transaction updates
    - Heartbeat events
    - Peer status changes
    - VDF checkpoints
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = WS_PORT,
    ):
        self.host = host
        self.port = port

        self._clients: Set[web.WebSocketResponse] = set()
        self._subscriptions: Dict[web.WebSocketResponse, List[Subscription]] = {}

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._running = False

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self):
        """Start the WebSocket server."""
        if self._running:
            return

        self._app = web.Application()
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_get("/", self._handle_info)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        self._running = True
        logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}/ws")

    async def stop(self):
        """Stop the WebSocket server."""
        if not self._running:
            return

        # Close all client connections
        for ws in list(self._clients):
            await ws.close()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._running = False
        logger.info("WebSocket server stopped")

    async def _handle_info(self, request: web.Request) -> web.Response:
        """Handle info request."""
        return web.json_response({
            "status": "ok",
            "clients": len(self._clients),
            "events": [e.name for e in WSEvent],
        })

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._clients.add(ws)
        self._subscriptions[ws] = []

        logger.info(f"WebSocket client connected: {request.remote}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")

        except Exception as e:
            logger.error(f"WebSocket handler error: {e}")

        finally:
            self._clients.discard(ws)
            self._subscriptions.pop(ws, None)
            logger.info(f"WebSocket client disconnected: {request.remote}")

        return ws

    async def _handle_message(self, ws: web.WebSocketResponse, data: str):
        """Handle message from client."""
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            await ws.send_json({"error": "Invalid JSON"})
            return

        action = msg.get("action")

        if action == "subscribe":
            event_name = msg.get("event")
            try:
                event_type = WSEvent[event_name.upper()]
                sub = Subscription(event_type=event_type, filter=msg.get("filter"))
                self._subscriptions[ws].append(sub)
                await ws.send_json({
                    "type": "subscribed",
                    "event": event_name,
                })
            except KeyError:
                await ws.send_json({"error": f"Unknown event: {event_name}"})

        elif action == "unsubscribe":
            event_name = msg.get("event")
            try:
                event_type = WSEvent[event_name.upper()]
                self._subscriptions[ws] = [
                    s for s in self._subscriptions[ws]
                    if s.event_type != event_type
                ]
                await ws.send_json({
                    "type": "unsubscribed",
                    "event": event_name,
                })
            except KeyError:
                await ws.send_json({"error": f"Unknown event: {event_name}"})

        elif action == "ping":
            await ws.send_json({"type": "pong"})

        else:
            await ws.send_json({"error": f"Unknown action: {action}"})

    async def broadcast(self, event_type: WSEvent, data: Dict):
        """
        Broadcast event to subscribed clients.

        Args:
            event_type: Type of event
            data: Event data
        """
        if not self._clients:
            return

        message = {
            "type": "event",
            "event": event_type.name.lower(),
            "data": data,
        }

        for ws in list(self._clients):
            if ws.closed:
                self._clients.discard(ws)
                continue

            # Check subscription
            subs = self._subscriptions.get(ws, [])
            for sub in subs:
                if sub.event_type == event_type:
                    # Apply filter if present
                    if sub.filter:
                        if not self._matches_filter(data, sub.filter):
                            continue

                    try:
                        await ws.send_json(message)
                    except Exception as e:
                        logger.error(f"Failed to send to client: {e}")
                    break

    def _matches_filter(self, data: Dict, filter: Dict) -> bool:
        """Check if data matches filter."""
        for key, value in filter.items():
            if key not in data:
                return False
            if data[key] != value:
                return False
        return True

    async def notify_new_block(self, block):
        """Notify clients of new block."""
        await self.broadcast(WSEvent.NEW_BLOCK, {
            "hash": block.hash().hex(),
            "height": block.height,
            "timestamp": block.timestamp_ms,
            "heartbeats": len(block.heartbeats),
            "transactions": len(block.transactions),
        })

    async def notify_new_transaction(self, tx_hash: Hash, tier: str, fee: int):
        """Notify clients of new transaction."""
        await self.broadcast(WSEvent.NEW_TRANSACTION, {
            "hash": tx_hash.hex(),
            "tier": tier,
            "fee": fee,
        })

    async def notify_new_heartbeat(self, node_id: Hash, tier: int, score: float):
        """Notify clients of new heartbeat."""
        await self.broadcast(WSEvent.NEW_HEARTBEAT, {
            "node_id": node_id.hex(),
            "tier": tier,
            "score": score,
        })

    async def notify_peer_connected(self, address: str, services: int):
        """Notify clients of peer connection."""
        await self.broadcast(WSEvent.PEER_CONNECTED, {
            "address": address,
            "services": services,
        })

    async def notify_peer_disconnected(self, address: str, reason: str):
        """Notify clients of peer disconnection."""
        await self.broadcast(WSEvent.PEER_DISCONNECTED, {
            "address": address,
            "reason": reason,
        })

    async def notify_sync_status(
        self,
        syncing: bool,
        current: int,
        target: int,
        progress: float,
    ):
        """Notify clients of sync status change."""
        await self.broadcast(WSEvent.SYNC_STATUS, {
            "syncing": syncing,
            "current_block": current,
            "target_block": target,
            "progress": progress,
        })

    async def notify_vdf_checkpoint(
        self,
        iterations: int,
        output: str,
        finality_level: str,
    ):
        """Notify clients of VDF checkpoint."""
        await self.broadcast(WSEvent.VDF_CHECKPOINT, {
            "iterations": iterations,
            "output": output,
            "finality_level": finality_level,
        })

    async def notify_finality_update(
        self,
        block_hash: str,
        level: str,
        accumulated: int,
    ):
        """Notify clients of finality update."""
        await self.broadcast(WSEvent.FINALITY_UPDATE, {
            "block_hash": block_hash,
            "finality_level": level,
            "accumulated_vdf": accumulated,
        })


def create_node_websocket(node, ws_server: WebSocketServer):
    """
    Wire up node events to WebSocket server.

    Args:
        node: FullNode instance
        ws_server: WebSocketServer instance
    """
    if hasattr(node, 'state_machine') and node.state_machine:
        node.state_machine.on_block_applied(
            lambda block: asyncio.create_task(ws_server.notify_new_block(block))
        )

    if hasattr(node, 'peer_manager') and node.peer_manager:
        node.peer_manager.on_peer_ready(
            lambda peer: asyncio.create_task(
                ws_server.notify_peer_connected(
                    f"{peer.address[0]}:{peer.address[1]}",
                    peer.info.services,
                )
            )
        )

        node.peer_manager.on_peer_disconnected(
            lambda peer, reason: asyncio.create_task(
                ws_server.notify_peer_disconnected(
                    f"{peer.address[0]}:{peer.address[1]}",
                    reason.name,
                )
            )
        )
