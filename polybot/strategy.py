"""The risk-free underpricing strategy.

For a binary market, holding one YES share and one NO share guarantees a $1
payout at resolution (exactly one resolves true). So if you can *buy* both
legs for less than $1 — best_ask(YES) + best_ask(NO) < 1 — the difference is
locked-in profit, independent of which way Bitcoin moves.

This module turns live books into :class:`ArbOpportunity` objects. It walks
depth so the executable size is the min of what each leg offers at a price
that still keeps the pair under $1 (net of fees and the required edge).
"""
from __future__ import annotations

import logging
from typing import Optional

from .config import Config
from .models import ArbOpportunity, Market, OrderBook

log = logging.getLogger("polybot.strategy")


def find_opportunity(
    cfg: Config,
    market: Market,
    yes_book: Optional[OrderBook],
    no_book: Optional[OrderBook],
) -> Optional[ArbOpportunity]:
    """Return an ArbOpportunity if both legs can be bought under $1 - edge.

    We take only the best ask on each side (the simple, robust version): for
    short-term BTC markets the top level is where the mispricing shows up and
    walking deeper risks moving the price past break-even. Size is capped by
    both books' top-level size and the configured per-order/per-level limits.
    """
    if yes_book is None or no_book is None:
        return None

    best_yes = yes_book.best_ask()
    best_no = no_book.best_ask()
    if best_yes is None or best_no is None:
        return None

    cost = best_yes.price + best_no.price

    # Fee model: a taker fee charged on each leg's notional eats into edge.
    fee = cfg.taker_fee * cost
    net_cost = cost + fee

    # Required: net_cost <= 1 - min_edge  ->  guaranteed profit after fees.
    if net_cost > 1.0 - cfg.min_edge:
        return None

    size = min(
        best_yes.size,
        best_no.size,
        cfg.order_size,
        cfg.max_size_per_level,
    )
    if size <= 0:
        return None

    opp = ArbOpportunity(
        market=market,
        yes_price=best_yes.price,
        no_price=best_no.price,
        size=size,
    )
    log.debug(
        "ARB %s | yes=%.3f no=%.3f cost=%.3f edge=%.3f size=%.2f profit=%.4f",
        market.question[:40],
        opp.yes_price,
        opp.no_price,
        opp.cost,
        opp.gross_edge,
        opp.size,
        opp.gross_profit,
    )
    return opp
