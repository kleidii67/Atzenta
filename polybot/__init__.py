"""polybot — a Polymarket risk-free arbitrage bot.

Detects YES+NO underpricing on short-term Bitcoin 'Up or Down' markets and
captures the locked-in spread. Paper mode by default; live trading is opt-in.
"""

from .config import CONFIG, Config

__all__ = ["CONFIG", "Config"]
__version__ = "0.1.0"
