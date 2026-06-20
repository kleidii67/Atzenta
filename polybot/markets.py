"""Discovery of short-term Bitcoin 'Up or Down' markets via the Gamma API.

These markets churn quickly (hourly / 15-min resolutions), so the bot
re-discovers the active set on an interval instead of hard-coding token IDs.
"""
from __future__ import annotations

import json
import logging
from typing import List

import httpx

from .config import Config
from .models import Market

log = logging.getLogger("polybot.markets")


def _parse_clob_token_ids(raw) -> list[str]:
    """Gamma returns clobTokenIds as a JSON-encoded string or a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    try:
        return [str(t) for t in json.loads(raw)]
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_outcomes(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(o) for o in raw]
    try:
        return [str(o) for o in json.loads(raw)]
    except (json.JSONDecodeError, TypeError):
        return []


def discover_markets(cfg: Config, client: httpx.Client) -> List[Market]:
    """Return active binary BTC Up/Down markets matching the configured query.

    We hit ``/markets`` with ``active=true&closed=false`` and filter client
    side by question text, because Gamma's text search is fuzzy.
    """
    markets: list[Market] = []
    seen: set[str] = set()

    for query in cfg.queries():
        try:
            resp = client.get(
                f"{cfg.gamma_host}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": 100,
                    "order": "endDate",
                    "ascending": "true",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Gamma market discovery failed for %r: %s", query, exc)
            continue

        for m in resp.json():
            question = (m.get("question") or "").strip()
            if query.lower() not in question.lower():
                continue

            token_ids = _parse_clob_token_ids(m.get("clobTokenIds"))
            if len(token_ids) != 2:
                continue  # only handle clean binary markets

            market_id = str(m.get("id") or m.get("conditionId") or question)
            if market_id in seen:
                continue
            seen.add(market_id)

            outcomes = _parse_outcomes(m.get("outcomes")) or ["Up", "Down"]
            try:
                tick = float(m.get("orderPriceMinTickSize") or 0.01)
            except (TypeError, ValueError):
                tick = 0.01

            markets.append(
                Market(
                    market_id=market_id,
                    question=question,
                    yes_token_id=token_ids[0],
                    no_token_id=token_ids[1],
                    yes_outcome=outcomes[0],
                    no_outcome=outcomes[1] if len(outcomes) > 1 else "Down",
                    end_date=m.get("endDate"),
                    tick_size=tick,
                    neg_risk=bool(m.get("negRisk", False)),
                )
            )

            if len(markets) >= cfg.max_markets:
                log.info("Hit max_markets=%d, stopping discovery", cfg.max_markets)
                return markets

    log.info("Discovered %d active BTC Up/Down market(s)", len(markets))
    return markets
