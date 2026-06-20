"""Entry point: ``python -m polybot``.

Loads a local ``.env`` if python-dotenv is available, configures logging, and
runs the bot until Ctrl-C.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from .bot import ArbBot
from .config import CONFIG


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def main() -> int:
    _load_dotenv()
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Re-read config after dotenv loaded the file.
    from .config import Config

    cfg = Config()
    try:
        cfg.require_live_creds()
    except RuntimeError as exc:
        logging.getLogger("polybot").error(str(exc))
        return 2

    bot = ArbBot(cfg)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.getLogger("polybot").info("Interrupted; shutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
