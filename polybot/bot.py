"""Orchestration: wire discovery + books + strategy + execution together.

Lifecycle:
  1. Discover active BTC Up/Down markets (Gamma).
  2. Open a websocket and stream every outcome token's order book.
  3. On each book update, re-evaluate that token's market for an arb.
  4. Fire the executor (paper or live) when an opportunity clears the edge
     and risk gates.
  5. Periodically re-discover markets (they expire) and resubscribe.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

import httpx

from .config import Config
from .executor import Executor
from .markets import discover_markets
from .models import Market
from .orderbook import OrderBookStore
from .strategy import find_opportunity

log = logging.getLogger("polybot.bot")


class ArbBot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.executor = Executor(cfg)
        self._http = httpx.Client()
        self._store: Optional[OrderBookStore] = None
        self._ws_task: Optional[asyncio.Task] = None
        # token_id -> Market, so a book update maps back to its pair.
        self._token_to_market: Dict[str, Market] = {}
        self._stop = asyncio.Event()

    # -- per-update evaluation ----------------------------------------------

    async def _on_book_update(self, token_id: str) -> None:
        market = self._token_to_market.get(token_id)
        if market is None or self._store is None:
            return

        yes_book = self._store.get(market.yes_token_id)
        no_book = self._store.get(market.no_token_id)
        opp = find_opportunity(self.cfg, market, yes_book, no_book)
        if opp is None:
            return

        result = self.executor.execute(opp)
        if result.ok:
            led = self.executor.ledger
            log.info(
                "Pairs=%d exposure=%.2f locked_profit=%.4f",
                led.trades,
                led.exposure,
                led.realized_edge,
            )
            if self.cfg.max_trades and led.trades >= self.cfg.max_trades:
                log.info("Reached max_trades; shutting down.")
                self.stop()

    # -- market subscription management -------------------------------------

    def _build_subscription(self, markets: list[Market]) -> list[str]:
        self._token_to_market.clear()
        token_ids: list[str] = []
        for m in markets:
            for tid in m.token_ids:
                self._token_to_market[tid] = m
                token_ids.append(tid)
        return token_ids

    async def _start_stream(self, markets: list[Market]) -> None:
        token_ids = self._build_subscription(markets)
        if not token_ids:
            log.warning("No tokens to subscribe to.")
            return
        self._store = OrderBookStore(self.cfg, token_ids)
        self._store.on_update(self._on_book_update)
        self._ws_task = asyncio.create_task(self._store.run())

    async def _restart_stream(self, markets: list[Market]) -> None:
        if self._store is not None:
            self._store.stop()
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        await self._start_stream(markets)

    # -- main loop -----------------------------------------------------------

    def stop(self) -> None:
        self._stop.set()
        if self._store is not None:
            self._store.stop()

    async def run(self) -> None:
        mode = "LIVE TRADING" if self.cfg.live_trading else "PAPER (dry-run)"
        log.info("Starting ArbBot in %s mode", mode)
        if self.cfg.live_trading:
            log.warning("LIVE_TRADING is ON — real orders will be placed!")

        markets = discover_markets(self.cfg, self._http)
        if not markets:
            log.error("No markets found for query %r; nothing to do.", self.cfg.market_query)
            return
        await self._start_stream(markets)

        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.cfg.market_refresh_secs
                    )
                except asyncio.TimeoutError:
                    pass
                if self._stop.is_set():
                    break
                # Periodic re-discovery: short-term markets roll over fast.
                fresh = discover_markets(self.cfg, self._http)
                fresh_tokens = {t for m in fresh for t in m.token_ids}
                current_tokens = set(self._token_to_market)
                if fresh and fresh_tokens != current_tokens:
                    log.info("Market set changed; resubscribing.")
                    await self._restart_stream(fresh)
        finally:
            self.stop()
            if self._ws_task is not None:
                self._ws_task.cancel()
                try:
                    await self._ws_task
                except asyncio.CancelledError:
                    pass
            self._http.close()
            led = self.executor.ledger
            log.info(
                "Shutdown. pairs=%d exposure=%.2f locked_profit=%.4f",
                led.trades,
                led.exposure,
                led.realized_edge,
            )
