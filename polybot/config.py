"""Configuration for the Polymarket arbitrage bot.

Everything sensitive (private key, API creds) comes from environment variables
so nothing secret ever lands in the repo. See ``.env.example`` for the full
list. Values are read once at import time into a single ``CONFIG`` object.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass
class Config:
    # --- Connectivity -------------------------------------------------------
    clob_host: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
    gamma_host: str = os.getenv("GAMMA_HOST", "https://gamma-api.polymarket.com")
    ws_url: str = os.getenv(
        "CLOB_WS_URL", "wss://ws-subscribe-clob.polymarket.com/ws/market"
    )
    chain_id: int = int(os.getenv("CHAIN_ID", "137"))  # Polygon mainnet

    # --- Credentials (only needed when LIVE_TRADING is on) ------------------
    private_key: Optional[str] = os.getenv("POLY_PRIVATE_KEY")
    api_key: Optional[str] = os.getenv("POLY_API_KEY")
    api_secret: Optional[str] = os.getenv("POLY_API_SECRET")
    api_passphrase: Optional[str] = os.getenv("POLY_API_PASSPHRASE")
    # Funder = the Polymarket proxy wallet that actually holds USDC. For
    # email/magic accounts this differs from the EOA derived from the key.
    funder: Optional[str] = os.getenv("POLY_FUNDER")
    # Signature type: 0 = EOA, 1 = email/magic proxy, 2 = browser proxy.
    signature_type: int = int(os.getenv("POLY_SIGNATURE_TYPE", "0"))

    # --- Safety -------------------------------------------------------------
    # The master switch. Even with a "live scaffold", real orders are only
    # ever sent when this is explicitly true. Default is paper/dry-run.
    live_trading: bool = _get_bool("LIVE_TRADING", False)

    # --- Market selection ---------------------------------------------------
    # Substring(s) used to discover the short-term BTC Up/Down markets on the
    # Gamma API. Comma-separated.
    market_query: str = os.getenv("MARKET_QUERY", "bitcoin up or down")
    # Hard limit on how many markets we watch at once.
    max_markets: int = int(os.getenv("MAX_MARKETS", "20"))
    # How often (seconds) to re-discover active markets (they expire fast).
    market_refresh_secs: float = _get_float("MARKET_REFRESH_SECS", 60.0)

    # --- Strategy parameters ------------------------------------------------
    # Minimum guaranteed edge (in cents of $1) to act on. ask_yes + ask_no
    # must be <= 1 - min_edge. 0.01 = at least 1 cent of risk-free profit
    # per share pair, before fees.
    min_edge: float = _get_float("MIN_EDGE", 0.01)
    # Per-leg order size in shares.
    order_size: float = _get_float("ORDER_SIZE", 5.0)
    # Don't take more than this depth from a single book level (shares).
    max_size_per_level: float = _get_float("MAX_SIZE_PER_LEVEL", 50.0)
    # Polymarket maker/taker fee as a fraction of notional. Used in the edge
    # calc so we don't chase phantom profit. (Currently 0 on Polymarket, but
    # kept configurable.)
    taker_fee: float = _get_float("TAKER_FEE", 0.0)

    # --- Risk limits --------------------------------------------------------
    # Max USDC notional deployed across all open arb legs at once.
    max_total_exposure: float = _get_float("MAX_TOTAL_EXPOSURE", 200.0)
    # Stop the whole bot after this many filled arb pairs (0 = unlimited).
    max_trades: int = int(os.getenv("MAX_TRADES", "0"))

    # --- Loop timing --------------------------------------------------------
    # How long to wait after a websocket book update before re-evaluating, to
    # debounce bursty updates (seconds).
    eval_debounce_secs: float = _get_float("EVAL_DEBOUNCE_SECS", 0.0)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def queries(self) -> list[str]:
        return [q.strip() for q in self.market_query.split(",") if q.strip()]

    def require_live_creds(self) -> None:
        """Raise a clear error if live trading is on but creds are missing."""
        if not self.live_trading:
            return
        missing = [
            name
            for name, val in (
                ("POLY_PRIVATE_KEY", self.private_key),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                "LIVE_TRADING=true but missing required credentials: "
                + ", ".join(missing)
                + ". Set them in your environment or turn LIVE_TRADING off."
            )


CONFIG = Config()
