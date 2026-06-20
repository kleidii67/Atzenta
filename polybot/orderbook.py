"""Real-time order book maintenance over the Polymarket CLOB websocket.

The market channel emits two relevant message types:
  * ``book``          – a full snapshot of one token's book
  * ``price_change``   – incremental level updates for one token

We keep an in-memory :class:`OrderBook` per token and invoke a callback after
every applied update so the strategy can react with minimal latency.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Dict, Iterable, Optional

import websockets

from .config import Config
from .models import BookSide, Level, OrderBook

log = logging.getLogger("polybot.orderbook")

UpdateCallback = Callable[[str], Awaitable[None]]


class OrderBookStore:
    """Holds live books for a set of tokens and keeps them fresh via WS."""

    def __init__(self, cfg: Config, token_ids: Iterable[str]):
        self.cfg = cfg
        self.token_ids = list(token_ids)
        self.books: Dict[str, OrderBook] = {
            tid: OrderBook(token_id=tid) for tid in self.token_ids
        }
        self._on_update: Optional[UpdateCallback] = None
        self._stop = asyncio.Event()

    def get(self, token_id: str) -> Optional[OrderBook]:
        return self.books.get(token_id)

    def on_update(self, cb: UpdateCallback) -> None:
        self._on_update = cb

    def stop(self) -> None:
        self._stop.set()

    # -- message handling ----------------------------------------------------

    def _apply_snapshot(self, msg: dict) -> Optional[str]:
        tid = msg.get("asset_id") or msg.get("market")
        book = self.books.get(tid)
        if book is None:
            return None
        book.asks = BookSide(
            levels=[
                Level(float(l["price"]), float(l["size"]))
                for l in msg.get("asks", [])
            ],
            is_ask=True,
        )
        book.bids = BookSide(
            levels=[
                Level(float(l["price"]), float(l["size"]))
                for l in msg.get("bids", [])
            ],
            is_ask=False,
        )
        book.asks.resort()
        book.bids.resort()
        return tid

    def _apply_price_change(self, msg: dict) -> Optional[str]:
        tid = msg.get("asset_id") or msg.get("market")
        book = self.books.get(tid)
        if book is None:
            return None
        for change in msg.get("changes", []):
            side = change.get("side", "").upper()
            price = float(change["price"])
            size = float(change["size"])
            target = book.asks if side in ("ASK", "SELL") else book.bids
            # Replace the level at this price (size 0 = remove).
            target.levels = [lv for lv in target.levels if lv.price != price]
            if size > 0:
                target.levels.append(Level(price, size))
            target.resort()
        return tid

    def _handle(self, raw: str) -> list[str]:
        """Parse a raw WS frame and return the token ids that changed."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        # The socket may batch several events into a list.
        events = data if isinstance(data, list) else [data]
        touched: list[str] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            etype = ev.get("event_type") or ev.get("type")
            tid: Optional[str] = None
            if etype == "book":
                tid = self._apply_snapshot(ev)
            elif etype == "price_change":
                tid = self._apply_price_change(ev)
            if tid:
                touched.append(tid)
        return touched

    # -- run loop ------------------------------------------------------------

    async def run(self) -> None:
        """Connect, subscribe, and keep books updated until stopped.

        Reconnects with exponential backoff on any connection drop.
        """
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.cfg.ws_url, ping_interval=10, ping_timeout=10
                ) as ws:
                    await ws.send(
                        json.dumps(
                            {"assets_ids": self.token_ids, "type": "market"}
                        )
                    )
                    log.info("Subscribed to %d token book(s)", len(self.token_ids))
                    backoff = 1.0
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        for tid in self._handle(raw):
                            if self._on_update is not None:
                                await self._on_update(tid)
            except (websockets.WebSocketException, OSError) as exc:
                if self._stop.is_set():
                    break
                log.warning(
                    "WS disconnected (%s); reconnecting in %.1fs", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
