"""Unit tests for the arbitrage detection — the heart of the bot.

Run with:  python -m pytest polybot/tests
These tests use no network and no credentials.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from polybot.config import Config
from polybot.models import BookSide, Level, Market, OrderBook
from polybot.strategy import find_opportunity


def _market() -> Market:
    return Market(
        market_id="m1",
        question="Bitcoin Up or Down — 3pm ET",
        yes_token_id="yes",
        no_token_id="no",
    )


def _book(token_id: str, ask_price: float, ask_size: float) -> OrderBook:
    return OrderBook(
        token_id=token_id,
        asks=BookSide(levels=[Level(ask_price, ask_size)], is_ask=True),
        bids=BookSide(levels=[], is_ask=False),
    )


def test_detects_underpricing():
    cfg = Config(min_edge=0.01, order_size=5, max_size_per_level=50, taker_fee=0.0)
    # 0.48 + 0.49 = 0.97  ->  3 cents of risk-free edge.
    yes = _book("yes", 0.48, 10)
    no = _book("no", 0.49, 8)
    opp = find_opportunity(cfg, _market(), yes, no)
    assert opp is not None
    assert abs(opp.cost - 0.97) < 1e-9
    assert abs(opp.gross_edge - 0.03) < 1e-9
    assert opp.size == 5  # capped by order_size
    assert abs(opp.gross_profit - 0.15) < 1e-9


def test_no_arb_when_sum_at_or_above_one():
    cfg = Config(min_edge=0.01)
    yes = _book("yes", 0.50, 10)
    no = _book("no", 0.51, 10)  # sums to 1.01
    assert find_opportunity(cfg, _market(), yes, no) is None


def test_min_edge_threshold_excludes_thin_spreads():
    cfg = Config(min_edge=0.02)
    yes = _book("yes", 0.49, 10)
    no = _book("no", 0.50, 10)  # 0.99 -> only 1 cent, below 2-cent floor
    assert find_opportunity(cfg, _market(), yes, no) is None


def test_size_capped_by_thinner_leg():
    cfg = Config(min_edge=0.01, order_size=100, max_size_per_level=100)
    yes = _book("yes", 0.40, 3)   # only 3 shares available
    no = _book("no", 0.45, 50)
    opp = find_opportunity(cfg, _market(), yes, no)
    assert opp is not None
    assert opp.size == 3


def test_fee_erodes_edge():
    # cost 0.98, but a 3% taker fee pushes net to ~1.0094 -> no arb at 1c edge.
    cfg = Config(min_edge=0.01, taker_fee=0.03)
    yes = _book("yes", 0.49, 10)
    no = _book("no", 0.49, 10)
    assert find_opportunity(cfg, _market(), yes, no) is None


def test_missing_book_returns_none():
    cfg = Config()
    assert find_opportunity(cfg, _market(), None, None) is None
