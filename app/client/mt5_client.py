"""Python client for the headless-mt5 REST API.

Wraps every endpoint exposed by the headless MT5 FastAPI service
(https://github.com/thanderoy/headless-mt5) so both the dashboard and the
automated trading engine can drive the MetaTrader 5 terminal cleanly.

Base URL defaults to http://localhost:5001 (the host-side bind configured in
the headless-mt5 docker-compose.yml).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

LOGGER = logging.getLogger("mt5client")

DEFAULT_BASE_URL = "http://localhost:5001"
API_PREFIX = "/api/v1"


class MT5Client:
    """Thin, typed wrapper around the headless-mt5 HTTP API."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        from app.config import MT5_API_BASE
        url = (base_url or MT5_API_BASE or DEFAULT_BASE_URL).rstrip("/")
        if url.endswith("/api/v1"):
            url = url[:-7]
        self.base_url = url
        self.timeout = timeout
        self.session = requests.Session()

    # ---- low-level helpers -------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.base_url}{API_PREFIX}{path}"

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        candidates = [self.base_url, "http://mt5:5001", "http://host.docker.internal:5001", "http://localhost:5001"]
        last_exc = None
        for candidate in dict.fromkeys(candidates):
            self.base_url = candidate.rstrip("/")
            if self.base_url.endswith("/api/v1"):
                self.base_url = self.base_url[:-7]
            try:
                resp = self.session.get(self._url(path), params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc

    def _post(self, path: str, json: Optional[dict] = None) -> Any:
        candidates = [self.base_url, "http://mt5:5001", "http://host.docker.internal:5001", "http://localhost:5001"]
        last_exc = None
        for candidate in dict.fromkeys(candidates):
            self.base_url = candidate.rstrip("/")
            if self.base_url.endswith("/api/v1"):
                self.base_url = self.base_url[:-7]
            try:
                resp = self.session.post(self._url(path), json=json or {}, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc

    # ---- connection / health ----------------------------------------------
    def health(self) -> Any:
        candidates = [self.base_url, "http://mt5:5001", "http://host.docker.internal:5001", "http://localhost:5001"]
        for candidate in dict.fromkeys(candidates):
            self.base_url = candidate.rstrip("/")
            if self.base_url.endswith("/api/v1"):
                self.base_url = self.base_url[:-7]
            try:
                return self.session.get(self.base_url + "/", timeout=self.timeout).json()
            except requests.exceptions.ConnectionError:
                continue
        return {}

    def connect(self, **params) -> Any:
        return self._post("/connect", params or None)

    def connect_broker(
        self,
        login: str,
        password: str,
        server: str,
        path: Optional[str] = None,
    ) -> Any:
        """Initialise + log into a broker account directly through the API."""
        params: Dict[str, Any] = {
            "login": int(login),
            "password": password,
            "server": server,
        }
        if path:
            params["path"] = path
        return self.connect(**params)

    def disconnect(self) -> Any:
        return self._post("/disconnect")

    # ---- account -----------------------------------------------------------
    def account(self) -> Dict[str, Any]:
        return self._get("/account")

    # ---- market data -------------------------------------------------------
    def rates(self, symbol: str, timeframe: str = "H1", count: int = 100) -> Dict[str, Any]:
        return self._get("/rates", {"symbol": symbol, "timeframe": timeframe, "count": count})

    def tick(self, symbol: str) -> Dict[str, Any]:
        return self._get("/tick", {"symbol": symbol})

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
        payload = {
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "order_type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return self._post("/order/send", payload)

    def close_position(self, ticket: int, volume: Optional[float] = None, deviation: int = 20, comment: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ticket": ticket, "deviation": deviation, "comment": comment}
        if volume is not None:
            payload["volume"] = volume
        return self._post("/order/close", payload)

    def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> Dict[str, Any]:
        return self._post("/order/modify", {"ticket": ticket, "sl": sl, "tp": tp})

    # ---- positions / history ----------------------------------------------
    def positions(self) -> List[Dict[str, Any]]:
        return self._get("/positions")

    def deals(self, from_time: Optional[datetime] = None, to_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if from_time:
            params["date_from"] = from_time.isoformat()
        if to_time:
            params["date_to"] = to_time.isoformat()
        return self._get("/deals", params)

    # ---- convenience -------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        """Aggregate the data most useful for a dashboard/engine in one call."""
        try:
            account = self.account()
        except Exception as exc:  # noqa: BLE001
            account = {"error": str(exc)}
        try:
            positions = self.positions()
        except Exception as exc:  # noqa: BLE001
            positions = {"error": str(exc)}
        return {"account": account, "positions": positions}
