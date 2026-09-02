#!/usr/bin/env python3
"""End-to-end verification of the forex trading stack.

Run once the MT5 container is up and logged in:
    ./scripts/trade.sh verify

Checks (in order):
  1. Docker container up
  2. MT5 REST API reachable (port 5001)
  3. Broker account info (login, balance, equity)
  4. Live rates for the configured symbols
  5. Strategy engine produces signals on real market data
  6. Broker positions/deals when available
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import build_client, DEFAULT_SYMBOLS      # noqa: E402
from app.engine.engine import Engine, RiskConfig      # noqa: E402


def banner(msg: str) -> None:
    print(f"\n=== {msg} ===")


def main() -> int:
    ok = True

    banner("1) MT5 container")
    from subprocess import run
    r = run(["docker", "ps", "--filter", "name=mt5", "--format", "{{.Status}}"],
            capture_output=True, text=True)
    status = r.stdout.strip()
    print(f"  container: {status or 'NOT RUNNING'}")
    if "Up" not in status:
        print("  FAIL: start with ./scripts/trade.sh up")
        return 1

    banner("2) Create client (auto-selects BROKER from .env)")
    try:
        client = build_client()
        print(f"  client: {type(client).__name__} @ {client.base_url}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL creating client: {e}")
        return 1

    banner("3) Broker connection + account")
    try:
        acct = client.account()
        print(f"  account: {acct}")
        ok = bool(acct and acct.get("balance") is not None)
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL account: {e}")
        print("  (If MT5 not logged in yet, do the broker login via "
              "http://localhost:3000 desktop, then re-run.)")
        return 1

    banner("4) Live rates for configured symbols")
    rates = {}
    try:
        for sym in DEFAULT_SYMBOLS:
            try:
                r_ = client.rates(sym)
                rates[sym] = r_
                last = r_[-1] if isinstance(r_, list) else r_
                print(f"  {sym}: {last}")
            except Exception as e:  # noqa: BLE001
                print(f"  {sym}: FAIL {e}")
                ok = False
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL rates: {e}")
        ok = False

    banner("5) Strategy engine signals on live data")
    try:
        cfg = RiskConfig()
        engine = Engine(client, cfg)
        sig = engine.evaluate(DEFAULT_SYMBOLS[0])
        print(f"  {DEFAULT_SYMBOLS[0]} evaluate(): {sig}")
        ok = ok and True  # a flat signal (None) is valid; connectivity already checked
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL engine: {e}")
        ok = False

    banner("6) Positions / deals (if any)")
    try:
        print(f"  positions: {client.positions()}")
        from datetime import datetime, timedelta
        print(f"  deals:     {client.deals(datetime.now() - timedelta(days=7), datetime.now())}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL positions/deals: {e}")

    print("\n" + ("END-TO-END: ALL OK" if ok else "END-TO-END: PARTIAL (see above)"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
