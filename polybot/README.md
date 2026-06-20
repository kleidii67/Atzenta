# polybot — Polymarket risk-free arbitrage bot

A small, modular Python bot that watches short-term **Bitcoin "Up or Down"**
prediction markets on Polymarket and captures the classic **YES + NO
underpricing** arbitrage.

## The idea

In a binary market, holding one **YES** share and one **NO** share guarantees
a **$1** payout at resolution — exactly one outcome resolves true. So whenever
both legs can be *bought* for less than a dollar:

```
best_ask(YES) + best_ask(NO) < $1.00
```

the difference is **locked-in profit**, regardless of which way Bitcoin moves.
On fast-resolving BTC Up/Down markets these gaps open and close in
milliseconds, so the bot streams the live order book over a websocket and
reacts to every update.

> This is genuine *risk-free* arbitrage (market-neutral), not a directional
> bet. The only real-world risks are execution risk (one leg fills, the other
> doesn't) and fees — both addressed below.

## Architecture

```
                   ┌──────────────┐
   Gamma REST  ───▶│  markets.py  │  discover active BTC Up/Down markets
                   └──────┬───────┘
                          │ token ids
                   ┌──────▼───────┐
   CLOB WS     ───▶│ orderbook.py │  live books, snapshot + price_change
                   └──────┬───────┘
                          │ on every update
                   ┌──────▼───────┐
                   │ strategy.py  │  ask_yes + ask_no < 1 - edge - fees?
                   └──────┬───────┘
                          │ ArbOpportunity
                   ┌──────▼───────┐
                   │ executor.py  │  paper fills  OR  live FOK orders
                   └──────────────┘   (risk gates: exposure, max trades)
        bot.py orchestrates + periodically re-discovers expiring markets
```

| File           | Responsibility |
|----------------|----------------|
| `config.py`    | Env-driven config + the `LIVE_TRADING` safety switch |
| `markets.py`   | Discover active markets via the Gamma API |
| `orderbook.py` | Maintain live books over the CLOB websocket (auto-reconnect) |
| `strategy.py`  | Detect the underpricing arb, net of edge + fees |
| `executor.py`  | Paper fills by default; live FOK orders when enabled |
| `bot.py`       | Wire it all together; re-subscribe as markets roll over |

## Install

```bash
cd polybot
pip install -r requirements.txt   # py-clob-client only needed for live mode
```

## Run (paper / dry-run — the default)

No credentials, no funds at risk. It connects to **live** Polymarket data,
detects real opportunities, and simulates the fills:

```bash
python -m polybot
```

You'll see lines like:

```
12:00:01 INFO    polybot.bot       | Starting ArbBot in PAPER (dry-run) mode
12:00:02 INFO    polybot.markets   | Discovered 6 active BTC Up/Down market(s)
12:00:02 INFO    polybot.orderbook | Subscribed to 12 token book(s)
12:00:05 INFO    polybot.executor  | [PAPER] bought 5.00x YES@0.480 + NO@0.490 cost=4.85 USDC locked_profit=0.1500
```

## Run (live trading — opt in)

> ⚠️ Live mode places **real orders with real USDC**. Read the code first.
> Start with a tiny `ORDER_SIZE` and a low `MAX_TOTAL_EXPOSURE`.

```bash
cp .env.example .env      # then fill in your credentials
# set LIVE_TRADING=true in .env
python -m polybot
```

Live mode uses the official [`py-clob-client`](https://github.com/Polymarket/py-clob-client)
to sign and post **fill-or-kill (FOK)** orders. FOK matters: each leg either
fills completely at your price or not at all, so the bot never ends up holding
a single naked leg.

## Configuration

All knobs are environment variables (see `.env.example`):

| Var | Default | Meaning |
|-----|---------|---------|
| `LIVE_TRADING` | `false` | Master switch. `false` = paper, never sends orders |
| `MARKET_QUERY` | `bitcoin up or down` | Substring(s) to match markets |
| `MIN_EDGE` | `0.01` | Minimum guaranteed profit per pair, in dollars |
| `ORDER_SIZE` | `5` | Shares per leg |
| `MAX_SIZE_PER_LEVEL` | `50` | Cap on shares taken from one book level |
| `TAKER_FEE` | `0.0` | Fee fraction folded into the edge calc |
| `MAX_TOTAL_EXPOSURE` | `200` | Max USDC deployed across open legs |
| `MAX_TRADES` | `0` | Stop after N pairs (0 = unlimited) |
| `MARKET_REFRESH_SECS` | `60` | How often to re-discover markets |

Credentials (`POLY_PRIVATE_KEY`, etc.) are only read in live mode. They live
in `.env`, which is git-ignored — **secrets never touch the repo**.

## Tests

```bash
python -m pytest polybot/tests -q
```

The tests cover the strategy core (detection, edge threshold, depth-limited
sizing, fee erosion) with no network and no credentials.

## Notes, limits & honest caveats

- **Execution risk.** Even with FOK, the two legs are two separate orders; the
  book can move between them. FOK on both is the mitigation, but in fast
  markets an opportunity may vanish before the second leg lands. The bot logs
  and aborts cleanly if the second leg fails.
- **Top-of-book only.** The strategy takes the best ask on each side and sizes
  to the thinner leg. It deliberately does *not* sweep deep levels (that would
  push the average price past break-even).
- **Fees & gas.** Defaults assume Polymarket's current 0% taker fee; set
  `TAKER_FEE` if that changes. On-chain settlement costs are not modeled.
- **Single infra, not 40 servers.** This is a clean reference implementation,
  not a co-located HFT stack. It's correct and readable first; latency tuning
  (regional hosting, connection pooling, order pre-signing) is left as an
  extension.
- **Compliance is on you.** Respect Polymarket's Terms of Service and the laws
  of your jurisdiction. This code is provided for educational/research use.
```
