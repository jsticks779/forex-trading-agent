"""OANDA v20 REST API client, mirroring the MT5 client interface.

Implements the same public methods as `client.mt5_client.MT5Client` so the
dashboard and engine can run against either backend by swapping the client
instance (MT5 container via REST, or OANDA directly).

OANDA runs as a normal Python process — no Docker, no Wine — and is reliable on
resource-constrained Linux boxes.

Credentials: OANDA_API_KEY and OANDA_ACCOUNT_ID, plus OANDA_ENV=practice|live.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

LOGGER = logging.getLogger("oandaclient")

# Symbol-name mapping: our generic names -> OANDA instrument names.
SYMBOL_MAP = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "USDCHF": "USD_CHF",
    "AUDUSD": "AUD_USD",
    "NZDUSD": "NZD_USD",
    "USDCAD": "USD_CAD",
    "XAUUSD": "XAU_USD",
}
REVERSE_MAP = {v: k for k, v in SYMBOL_MAP.items()}

BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# MT5-timeframe to OANDA candlestick granularity.
GRANULARITY = {
    "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
    "H1": "H1", "H4": "H4", "D1": "D", "W1": "W", "MN1": "M",
}


class OandaClient:
    def __init__(self, api_key: str, account_id: str, env: str = "practice", timeout: int = 30):
        self.api_key = api_key
        self.account_id = account_id
        self.base = BASE_URLS.get(env, BASE_URLS["practice"])
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    # ---- connection (OANDA is stateless-ish; just a health check) ---------
    def health(self) -> Any:
        # ping the account endpoint
        return self.account()

    def connect(self, **params) -> Any:
        return {"success": True, "message": "OANDA REST is stateless; nothing to init."}

    def connect_broker(self, login, password, server, path=None) -> Any:
        return self.connect()

    def disconnect(self) -> Any:
        return {"success": True, "message": "OANDA REST has no persistent connection."}

    # ---- account -----------------------------------------------------------
    def account(self) -> Dict[str, Any]:
        r = self.session.get(
            f"{self.base}/v3/accounts/{self.account_id}", timeout=self.timeout
        )
        r.raise_for_status()
        a = r.json()["account"]
        return {
            "login": int(a.get("id", 0)),
            "balance": float(a.get("balance", 0)),
            "equity": float(a.get("NAV", a.get("balance", 0))),
            "margin": float(a.get("marginUsed", 0)),
            "margin_free": float(a.get("marginAvailable", 0)),
            "margin_level": float(a.get("marginCallMarginUsed", 0)) or 0,
            "profit": float(a.get("unrealizedPL", 0)),
            "currency": a.get("currency", "USD"),
            "leverage": 0,
            "name": a.get("alias", a.get("id", "")),
            "server": self.base,
            "trade_mode": 0,
        }

    # ---- market data -------------------------------------------------------
    def _instrument(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    def _back(self, instr: str) -> str:
        return REVERSE_MAP.get(instr, instr)

    def rates(self, symbol: str, timeframe: str = "H1", count: int = 100) -> Dict[str, Any]:
        instr = self._instrument(symbol)
        gran = GRANULARITY.get(timeframe.upper(), "H1")
        r = self.session.get(
            f"{self.base}/v3/instruments/{instr}/candles",
            params={"granularity": gran, "count": min(count, 5000)},
            timeout=self.timeout,
        )
        r.raise_for_status()
        candles = r.json().get("candles", [])
        rates = []
        for c in candles:
            mid = c.get("mid", {})
            rates.append({
                "time": c.get("time"),
                "open": float(mid.get("o", 0)),
                "high": float(mid.get("h", 0)),
                "low": float(mid.get("l", 0)),
                "close": float(mid.get("c", 0)),
                "tick_volume": int(c.get("volume", 0)),
                "spread": 0,
                "real_volume": int(c.get("volume", 0)),
            })
        # MT5/Kasm engine expects 'rates' key with ascending oldest->newest
        return {"symbol": symbol, "timeframe": timeframe, "count": len(rates), "rates": rates[::-1]}

    def tick(self, symbol: str) -> Dict[str, Any]:
        instr = self._instrument(symbol)
        r = self.session.get(
            f"{self.base}/v3/instruments/{instr}/candles",
            params={"granularity": "S5", "price": "BA", "count": 1},
            timeout=self.timeout,
        )
        r.raise_for_status()
        c = r.json()["candles"][-1]
        bid = c.get("bid", {}).get("c", "0")
        ask = c.get("ask", {}).get("c", "0")
        return {
            "symbol": symbol,
            "bid": float(bid),
            "ask": float(ask),
            "last": float(ask),
            "volume": float(c.get("volume", 0)),
            "time": c.get("time"),
        }

    # ---- trading -----------------------------------------------------------
    def send_order(
        self,
        symbol: str,
        action: str,
        volume: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "",
    ) -> Dict[str, Any]:
        instr = self._instrument(symbol)
        units = self._units(action, volume)
        body: Dict[str, Any] = {"order": {"units": units}}
        if order_type.upper() == "MARKET":
            body["order"]["type"] = "MARKET"
            body["order"]["timeInForce"] = "FOK"
        elif order_type.upper() == "LIMIT":
            body["order"]["type"] = "LIMIT"
            body["order"]["price"] = str(price)
            body["order"]["timeInForce"] = "GTC"
        else:  # STOP market order
            body["order"]["type"] = "STOP"
            body["order"]["price"] = str(price)
            body["order"]["timeInForce"] = "GTC"

        # dynamic SL/TP as separate attached orders
        if sl is not None:
            body["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}"}
        if tp is not None:
            body["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}"}
        body["order"]["clientExtensions"] = {"tag": str(magic), "comment": comment or "eng"}

        r = self.session.post(
            f"{self.base}/v3/accounts/{self.account_id}/orders", json=body, timeout=self.timeout
        )
        r.raise_for_status()
        data = r.json()
        order = data.get("orderFillTransaction") or data.get("orderCreateTransaction", {})
        success = "Fill" in data or "orderFillTransaction" in data
        return {
            "success": success,
            "order": order.get("tradeID") or order.get("id"),
            "volume": volume,
            "price": (data.get("orderFillTransaction") or {}).get("price"),
            "retcode": 0 if success else 1,
            "retcode_description": "DONE" if success else "REJECT",
            "comment": str(data.get("lastTransactionID", "")),
        }

    def _units(self, action: str, volume: float) -> int:
        n = int(round(volume * 100000))
        return n if action.upper() == "BUY" else -n

    def positions(self) -> List[Dict[str, Any]]:
        r = self.session.get(
            f"{self.base}/v3/accounts/{self.account_id}/openPositions",
            timeout=self.timeout,
        )
        r.raise_for_status()
        out = []
        for p in r.json().get("positions", []):
            if p.get("long", {}).get("units", 0) not in (0, "0"):
                units = int(p["long"]["units"])
                side = 0
                price = float(p["long"].get("averagePrice", 0))
                pl = float(p["long"].get("unrealizedPL", 0))
            else:
                units = int(p["short"]["units"])
                side = 1
                price = float(p["short"].get("averagePrice", 0))
                pl = float(p["short"].get("unrealizedPL", 0))
            t = self.tick(self._back(p["instrument"]))
            out.append({
                "ticket": hash(p["instrument"]) & 0x7fffffff,
                "symbol": self._back(p["instrument"]),
                "type": side,
                "type_description": "POSITION_TYPE_BUY" if side == 0 else "POSITION_TYPE_SELL",
                "volume": abs(units) / 100000,
                "price_open": price,
                "price_current": t.get("bid") if side == 0 else t.get("ask"),
                "profit": pl,
                "sl": float(p.get("stopLossOrder", {}) or {}).get("price", 0) or 0,
                "tp": float(p.get("takeProfitOrder", {}) or {}).get("price", 0) or 0,
                "time": None,
                "magic": 0,
                "comment": "",
                "swap": 0.0,
                "commission": 0.0,
            })
        return out

    def close_position(self, ticket: int, volume: Optional[float] = None, deviation: int = 20, comment: str = "") -> Dict[str, Any]:
        pos = next((p for p in self.positions() if p["ticket"] == ticket), None)
        if not pos:
            return {"success": False, "retcode_description": "POSITION_NOT_FOUND", "comment": ""}
        instr = self._instrument(pos["symbol"])
        units = int(round(pos["volume"] * 100000))
        units = -units if pos["type"] == 0 else units  # opposite sign to close
        body = {"order": {"type": "MARKET", "timeInForce": "FOK", "units": units,
                          "positionFill": "REDUCE_ONLY"}}
        try:
            r = self.session.post(
                f"{self.base}/v3/accounts/{self.account_id}/orders", json=body, timeout=self.timeout
            )
            r.raise_for_status()
            data = r.json()
            return {"success": True, "retcode_description": "DONE", "comment": data.get("lastTransactionID", ""), "order": data.get("orderFillTransaction", {}).get("tradeID")}
        except requests.HTTPError as exc:
            return {"success": False, "retcode_description": f"HTTP {exc.response.status_code}", "comment": exc.response.text[:200]}

    def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> Dict[str, Any]:
        pos = next((p for p in self.positions() if p["ticket"] == ticket), None)
        if not pos:
            return {"success": False, "retcode_description": "POSITION_NOT_FOUND", "comment": ""}
        instr = self._instrument(pos["symbol"])
        # find the open trade id
        r = self.session.get(
            f"{self.base}/v3/accounts/{self.account_id}/openTrades", timeout=self.timeout
        )
        r.raise_for_status()
        trade = next((t for t in r.json().get("trades", []) if t["instrument"] == instr), None)
        if not trade:
            return {"success": False, "retcode_description": "TRADE_NOT_FOUND", "comment": ""}
        tid = trade["id"]
        body: Dict[str, Any] = {}
        if sl is not None:
            body["stopLoss"] = {"price": f"{sl:.5f}"}
        if tp is not None:
            body["takeProfit"] = {"price": f"{tp:.5f}"}
        rr = self.session.put(
            f"{self.base}/v3/accounts/{self.account_id}/trades/{tid}/orders",
            json=body, timeout=self.timeout,
        )
        rr.raise_for_status()
        return {"success": True, "retcode_description": "DONE", "comment": rr.json().get("lastTransactionID", "")}

    def deals(self, from_time: Optional[datetime] = None, to_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"type": "ORDER_FILL"}
        if from_time:
            params["from"] = from_time.isoformat()
            params["to"] = (to_time or datetime.now(timezone.utc)).isoformat()
        r = self.session.get(
            f"{self.base}/v3/accounts/{self.account_id}/transactions",
            params=params, timeout=self.timeout,
        )
        r.raise_for_status()
        out = []
        for tx in r.json().get("transactions", []):
            if tx.get("type") != "ORDER_FILL":
                continue
            out.append({
                "time": tx.get("time"),
                "type_description": "DEAL_TYPE_BUY" if tx.get("units", 0) > 0 else "DEAL_TYPE_SELL",
                "symbol": self._back(tx.get("instrument", "")),
                "volume": abs(tx.get("units", 0)) / 100000,
                "price": tx.get("price"),
                "profit": float(tx.get("pl", 0)),
                "magic": tx.get("clientExtensions", {}).get("tag", 0),
                "comment": tx.get("clientExtensions", {}).get("comment", ""),
            })
        return out
