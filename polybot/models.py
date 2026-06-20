"""Lightweight data models shared across the bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Level:
    """A single price level in an order book."""

    price: float
    size: float


@dataclass
class BookSide:
    """One side (bids or asks) of a book, kept sorted on update.

    Asks are sorted ascending (best = lowest), bids descending (best =
    highest). We keep the raw levels so the strategy can walk depth.
    """

    levels: List[Level] = field(default_factory=list)
    is_ask: bool = True

    def best(self) -> Optional[Level]:
        return self.levels[0] if self.levels else None

    def resort(self) -> None:
        self.levels.sort(key=lambda lv: lv.price, reverse=not self.is_ask)


@dataclass
class OrderBook:
    """Top-of-book + depth for a single outcome token."""

    token_id: str
    asks: BookSide = field(default_factory=lambda: BookSide(is_ask=True))
    bids: BookSide = field(default_factory=lambda: BookSide(is_ask=False))

    def best_ask(self) -> Optional[Level]:
        return self.asks.best()

    def best_bid(self) -> Optional[Level]:
        return self.bids.best()


@dataclass
class Market:
    """A binary BTC Up/Down market: two complementary outcome tokens."""

    market_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_outcome: str = "Up"
    no_outcome: str = "Down"
    end_date: Optional[str] = None
    tick_size: float = 0.01
    neg_risk: bool = False

    @property
    def token_ids(self) -> Tuple[str, str]:
        return (self.yes_token_id, self.no_token_id)


@dataclass
class ArbOpportunity:
    """A detected risk-free underpricing: ask_yes + ask_no < 1."""

    market: Market
    yes_price: float
    no_price: float
    size: float  # shares we can take on both legs

    @property
    def cost(self) -> float:
        """USDC paid per share-pair."""
        return self.yes_price + self.no_price

    @property
    def gross_edge(self) -> float:
        """Guaranteed profit per share-pair at resolution, before fees."""
        return 1.0 - self.cost

    @property
    def notional(self) -> float:
        return self.cost * self.size

    @property
    def gross_profit(self) -> float:
        return self.gross_edge * self.size
