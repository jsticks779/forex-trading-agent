"""Shared configuration for the forex trading dashboard + engine."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (next to this package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# MT5 REST API (headless-mt5 container).
_default_api = "http://mt5:5001" if os.path.exists("/.dockerenv") else "http://localhost:5001"
MT5_API_BASE = os.getenv("MT5_API_BASE", _default_api)

# Backend to use: "mt5" (REST container) or "oanda" (direct REST).
BROKER = os.getenv("BROKER", "mt5").lower()

# OANDA credentials (used when BROKER=oanda).
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENV = os.getenv("OANDA_ENV", "practice").lower()

# Default symbols to watch.
DEFAULT_SYMBOLS = [
    sym.strip()
    for sym in os.getenv(
        "SYMBOLS",
        "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,NZDUSD,USDCAD",
    ).split(",")
    if sym.strip()
]

# Magic number used to tag the AI engine's own orders so it can identify them.
ENGINE_MAGIC = int(os.getenv("ENGINE_MAGIC", "2460000"))


def build_client() -> "object":
    """Return the appropriate broker client based on BROKER."""
    if BROKER == "oanda":
        if not OANDA_API_KEY or not OANDA_ACCOUNT_ID:
            raise RuntimeError(
                "BROKER=oanda but OANDA_API_KEY / OANDA_ACCOUNT_ID are not set. "
                "Set them in the .env or export them."
            )
        from app.client.oanda_client import OandaClient
        return OandaClient(
            api_key=OANDA_API_KEY,
            account_id=OANDA_ACCOUNT_ID,
            env=OANDA_ENV,
        )
    from app.client.mt5_client import MT5Client
    return MT5Client(base_url=MT5_API_BASE)
