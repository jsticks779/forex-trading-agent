"""Automated trading engine for the MT5 setup.

A risk-managed strategy runner that drives the headless-mt5 REST API. It scans
a watchlist, computes simple technical signals, manages risk, and opens/closes
positions tagged with a dedicated magic number so the dashboard can tell the
engine's trades apart from manual ones.

This is a demonstration/educational engine — it is intentionally conservative.
**Trading real or demo money involves substantial risk.**

Run (one cycle) with:
    python -m app.engine run --once

Run continuously:
    python -m app.engine run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.client.mt5_client import MT5Client  # noqa: E402
from app.config import DEFAULT_SYMBOLS, ENGINE_MAGIC, MT5_API_BASE, build_client  # noqa: E402

LOGGER = logging.getLogger("engine")


# ------------------------------------------------------------------ signals
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def fastrsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


class RiskConfig:
    """Tunable risk parameters."""

    def __init__(
        self,
        max_positions: int = 3,
        risk_per_trade: float = 0.01,      # fraction of equity per trade
        max_daily_loss_frac: float = 0.03, # stop trading after losing 3% of equity/day
        sl_mult_atr: float = 1.5,
        tp_mult_atr: float = 2.0,
        magic: int = ENGINE_MAGIC,
    ):
        self.max_positions = max_positions
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss_frac = max_daily_loss_frac
        self.sl_mult_atr = sl_mult_atr
        self.tp_mult_atr = tp_mult_atr
        self.magic = magic


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr_val = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def position_size(equity: float, risk_frac: float, stop_distance: float, value_per_lot: float) -> float:
    """Lots sized so a full stop-loss move risks `risk_frac` of equity."""
    if stop_distance <= 0 or value_per_lot <= 0:
        return 0.0
    dollars_at_risk = equity * risk_frac
    lots = dollars_at_risk / (stop_distance * value_per_lot)
    return max(0.01, round(lots * 100) / 100)  # round to 0.01 lot


class Engine:
    """Risk-managed indicator engine."""

    def __init__(
        self,
        client: MT5Client,
        risk: Optional[RiskConfig] = None,
        watchlist: Optional[List[str]] = None,
        timeframe: str = "H1",
    ):
        self.client = client
        self.risk = risk or RiskConfig()
        self.watchlist = watchlist or DEFAULT_SYMBOLS
        self.timeframe = timeframe

    def _my_positions(self) -> List[Dict]:
        positions = self.client.positions()
        return [p for p in positions if p.get("magic") == self.risk.magic]

    def _manage_open_positions(self) -> None:
        """Move Stop Loss to breakeven once price moves +1.0x ATR in profit."""
        positions = self._my_positions()
        for pos in positions:
            ticket = pos.get("ticket")
            p_type = pos.get("type_description", "")
            price_open = pos.get("price_open", 0)
            price_curr = pos.get("price_current", 0)
            sl = pos.get("sl", 0)
            tp = pos.get("tp", 0)
            symbol = pos.get("symbol", "")

            rates = self.client.rates(symbol, self.timeframe, 50)
            if not rates.get("rates"):
                continue
            df = pd.DataFrame(rates["rates"])
            a = atr(df).iloc[-1]
            if pd.isna(a) or a <= 0:
                continue

            # Check breakeven condition (move SL to entry price)
            if "BUY" in p_type and price_curr >= price_open + 1.0 * a and sl < price_open:
                LOGGER.info("Moving BUY position #%d (%s) SL to Breakeven @ %.5f", ticket, symbol, price_open)
                self.client.modify_position(ticket, sl=round(price_open, 5), tp=tp)
            elif "SELL" in p_type and price_curr <= price_open - 1.0 * a and (sl > price_open or sl == 0):
                LOGGER.info("Moving SELL position #%d (%s) SL to Breakeven @ %.5f", ticket, symbol, price_open)
                self.client.modify_position(ticket, sl=round(price_open, 5), tp=tp)

    def _daily_pnl(self) -> float:
        """P/L from deals today (entries + exits), from engine magic trades."""
        from datetime import datetime, timedelta
        start = datetime.now() - timedelta(days=1)
        deals = self.client.deals(start, datetime.now())
        total = 0.0
        for d in deals:
            if d.get("magic") == self.risk.magic:
                total += d.get("profit", 0) + d.get("swap", 0) + d.get("commission", 0)
        return total

    def evaluate(self, symbol: str) -> Optional[Dict]:
        """Return a suggested trade for symbol, or None."""
        rates = self.client.rates(symbol, self.timeframe, 200)
        if not rates.get("rates"):
            return None
        df = pd.DataFrame(rates["rates"])
        close = df["close"]
        atr_s = atr(df)
        adx_s = adx(df)

        short_ema = ema(close, 20)
        long_ema = ema(close, 50)
        rsi = fastrsi(close)
        macd_line, signal_line = macd(close)

        last = df.iloc[-1]
        a = atr_s.iloc[-1]
        adx_val = adx_s.iloc[-1]
        if pd.isna(a) or a <= 0 or pd.isna(adx_val):
            return None

        # Require strong trend (ADX >= 20)
        trend_strong = adx_val >= 20.0
        trend_ema = ema(close, 200)
        trend_up = trend_strong and short_ema.iloc[-1] > long_ema.iloc[-1] and close.iloc[-1] > trend_ema.iloc[-1]
        trend_dn = trend_strong and short_ema.iloc[-1] < long_ema.iloc[-1] and close.iloc[-1] < trend_ema.iloc[-1]
        rsi_last = rsi.iloc[-1]
        macd_bull = macd_line.iloc[-1] > signal_line.iloc[-1]
        macd_bear = macd_line.iloc[-1] < signal_line.iloc[-1]

        tick = self.client.tick(symbol)

        if trend_up and rsi_last < 60 and macd_bull:
            entry = tick["ask"]
            stop = entry - self.risk.sl_mult_atr * a
            target = entry + 2.5 * a
            return {
                "symbol": symbol, "action": "BUY", "entry": entry,
                "stop": stop, "target": target, "atr": a,
            }
        if trend_dn and rsi_last > 40 and macd_bear:
            entry = tick["bid"]
            stop = entry + self.risk.sl_mult_atr * a
            target = entry - 2.5 * a
            return {
                "symbol": symbol, "action": "SELL", "entry": entry,
                "stop": stop, "target": target, "atr": a,
            }
        return None

    def run_once(self) -> Dict:
        """Run a single scan cycle. Returns a report dict."""
        report: Dict = {"checks": [], "trades": [], "skipped": []}

        # 1. Manage open positions (e.g. move SL to breakeven when in profit)
        try:
            self._manage_open_positions()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Position management error: %s", exc)

        account = self.client.account()
        equity = account.get("equity", 0)
        my_positions = self._my_positions()

        if len(my_positions) >= self.risk.max_positions:
            report["skipped"].append("max positions reached")
            return report

        daily_pnl = self._daily_pnl()
        if daily_pnl <= -equity * self.risk.max_daily_loss_frac:
            report["skipped"].append("daily loss limit hit")
            return report

        for symbol in self.watchlist:
            if len(my_positions) >= self.risk.max_positions:
                break
            existing = [p for p in my_positions if p["symbol"] == symbol]
            if existing:
                continue
            try:
                signal = self.evaluate(symbol)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("eval %s failed: %s", symbol, exc)
                continue
            if not signal:
                continue

            stop_distance = abs(signal["entry"] - signal["stop"])
            # Rough $/point per lot for sizing is symbol-dependent; fall back to a
            # simple conservative fixed fraction of equity when the tick size is known.
            # For demo sizing we use a placeholder value_per_lot.
            tick = self.client.tick(symbol)
            # For standard FX pairs (100k contract size), 1 lot = $100,000 per 1.0 price move
            value_per_lot = 100000.0
            lots = position_size(equity, self.risk.risk_per_trade, stop_distance, value_per_lot)

            res = self.client.send_order(
                symbol=symbol,
                action=signal["action"],
                volume=lots,
                order_type="MARKET",
                sl=round(signal["stop"], 5),
                tp=round(signal["target"], 5),
                magic=self.risk.magic,
                comment="eng",
            )
            report["trades"].append(
                {
                    "symbol": symbol,
                    "action": signal["action"],
                    "volume": lots,
                    "result": res.get("success"),
                    "retcode": res.get("retcode_description"),
                }
            )
            LOGGER.info("opened %s %s %.2f -> %s", signal["action"], symbol, lots, res)
            my_positions = self._my_positions()

        return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MT5 automated trading engine")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--once", action="store_true", help="run a single cycle")
    parser.add_argument("--interval", type=int, default=60, help="seconds between cycles")
    parser.add_argument("--timeframe", default="H1", choices=["M15", "M30", "H1", "H4", "D1"], help="signal timeframe")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="comma-separated watchlist")
    parser.add_argument("--max-positions", type=int, default=3)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    client = build_client()
    risk = RiskConfig(max_positions=args.max_positions)
    engine = Engine(client, risk=risk, watchlist=args.symbols.split(","), timeframe=args.timeframe)

    if args.once:
        print(engine.run_once())
        return 0

    LOGGER.info("Starting continuous engine (Ctrl+C to stop)")
    try:
        while True:
            try:
                report = engine.run_once()
                LOGGER.info("cycle done: %d trades, %d checks", len(report["trades"]), len(report["checks"]))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("cycle error: %s", exc)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOGGER.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
