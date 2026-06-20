"""Order execution layer.

Two modes, selected by ``CONFIG.live_trading``:

* **dry-run (default)** – logs the orders it *would* place and books simulated
  fills against the opportunity. No network calls, no funds at risk. This is
  the safe default even in the "live scaffold" build.
* **live** – signs and posts real FOK (fill-or-kill) orders through
  ``py_clob_client`` using credentials from the environment.

Both paths go through :meth:`Executor.execute`, which places the two arb legs
as close to simultaneously as possible and tracks running exposure / PnL.

py_clob_client is imported lazily so paper mode works without it installed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import Config
from .models import ArbOpportunity

log = logging.getLogger("polybot.executor")


@dataclass
class ExecResult:
    ok: bool
    opp: ArbOpportunity
    detail: str = ""


@dataclass
class Ledger:
    """Tracks what the bot has done so we can enforce risk limits."""

    trades: int = 0
    exposure: float = 0.0  # USDC currently deployed in arb legs
    realized_edge: float = 0.0  # guaranteed profit locked in (gross)

    def record(self, opp: ArbOpportunity) -> None:
        self.trades += 1
        self.exposure += opp.notional
        self.realized_edge += opp.gross_profit


class Executor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ledger = Ledger()
        self._client = None  # lazily created py_clob_client.ClobClient
        if cfg.live_trading:
            self._init_live_client()

    # -- live client setup ---------------------------------------------------

    def _init_live_client(self) -> None:
        self.cfg.require_live_creds()
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "LIVE_TRADING=true requires py-clob-client. "
                "Install with: pip install py-clob-client"
            ) from exc

        client = ClobClient(
            self.cfg.clob_host,
            key=self.cfg.private_key,
            chain_id=self.cfg.chain_id,
            signature_type=self.cfg.signature_type,
            funder=self.cfg.funder,
        )

        # Use provided API creds, or derive them from the private key.
        if self.cfg.api_key and self.cfg.api_secret and self.cfg.api_passphrase:
            client.set_api_creds(
                ApiCreds(
                    api_key=self.cfg.api_key,
                    api_secret=self.cfg.api_secret,
                    api_passphrase=self.cfg.api_passphrase,
                )
            )
        else:
            log.info("Deriving API credentials from private key...")
            client.set_api_creds(client.create_or_derive_api_creds())

        self._client = client
        log.info("Live CLOB client ready (chain_id=%d)", self.cfg.chain_id)

    # -- risk gate -----------------------------------------------------------

    def can_trade(self, opp: ArbOpportunity) -> tuple[bool, str]:
        if self.cfg.max_trades and self.ledger.trades >= self.cfg.max_trades:
            return False, "max_trades reached"
        if self.ledger.exposure + opp.notional > self.cfg.max_total_exposure:
            return False, "max_total_exposure would be exceeded"
        return True, ""

    # -- execution -----------------------------------------------------------

    def execute(self, opp: ArbOpportunity) -> ExecResult:
        allowed, why = self.can_trade(opp)
        if not allowed:
            return ExecResult(False, opp, f"blocked: {why}")

        if not self.cfg.live_trading:
            return self._execute_paper(opp)
        return self._execute_live(opp)

    def _execute_paper(self, opp: ArbOpportunity) -> ExecResult:
        self.ledger.record(opp)
        detail = (
            f"[PAPER] bought {opp.size:.2f}x YES@{opp.yes_price:.3f} + "
            f"NO@{opp.no_price:.3f} cost={opp.notional:.2f} USDC "
            f"locked_profit={opp.gross_profit:.4f}"
        )
        log.info(detail)
        return ExecResult(True, opp, detail)

    def _execute_live(self, opp: ArbOpportunity) -> ExecResult:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY

        legs = (
            (opp.market.yes_token_id, opp.yes_price, opp.market.yes_outcome),
            (opp.market.no_token_id, opp.no_price, opp.market.no_outcome),
        )
        placed = []
        for token_id, price, label in legs:
            args = OrderArgs(
                token_id=token_id,
                price=price,
                size=opp.size,
                side=BUY,
            )
            try:
                signed = self._client.create_order(args)
                # FOK: either both shares fill at our price or nothing does,
                # so we never end up holding a single naked leg.
                resp = self._client.post_order(signed, OrderType.FOK)
            except Exception as exc:  # noqa: BLE001 - surface any SDK error
                log.error("Live order failed on %s leg: %s", label, exc)
                return ExecResult(
                    False,
                    opp,
                    f"live order failed on {label} leg: {exc}; "
                    f"placed so far={placed}",
                )
            placed.append({"leg": label, "resp": resp})

        self.ledger.record(opp)
        detail = f"[LIVE] filled arb pair: {placed}"
        log.info(detail)
        return ExecResult(True, opp, detail)
