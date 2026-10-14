"""Stdlib-only HTTP client for the DAiL marketplace API.

Auth: `Authorization: Bearer <api_key>` works for both reads and writes.
(Verified live 2026-10-14: X-Agent-Key returns 401.)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE = "https://dail-3dci.onrender.com"


class DailError(RuntimeError):
    """Raised for non-2xx responses. Carries status, body and the request path."""

    def __init__(self, status: int, path: str, body: str):
        self.status = status
        self.path = path
        self.body = body
        super().__init__(f"HTTP {status} on {path}: {body[:300]}")


@dataclass
class DailClient:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE
    agent_id: str | None = None
    timeout: float = 60.0

    def _request(self, method: str, path: str, body: Any = None,
                 auth: bool = True, timeout: float | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "User-Agent": "dail-radar/0.1"}
        if auth:
            if not self.api_key:
                raise DailError(0, path, "api_key required for this call")
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + path, data=data,
                                     method=method, headers=headers)
        try:
            r = urllib.request.urlopen(req, timeout=timeout or self.timeout)
            raw = r.read().decode()
        except urllib.error.HTTPError as e:
            raise DailError(e.code, path, e.read().decode(errors="replace")) from None
        return json.loads(raw) if raw else None

    # ---- reads (5 real endpoints) ----
    def health(self) -> dict:
        return self._request("GET", "/health", auth=False)

    def stats(self) -> dict:
        return self._request("GET", "/world/stats", auth=False)

    def state(self) -> dict:
        return self._request("GET", "/world/state")

    def open_bounties(self, limit: int = 200, status: str = "open") -> list[dict]:
        q = f"/world/bounties?limit={int(limit)}"
        if status:
            q += f"&status={status}"
        return self._request("GET", q).get("bounties", [])

    def bounties(self, limit: int = 200, status: str = "") -> list[dict]:
        return self.open_bounties(limit=limit, status=status)

    def bounty(self, bounty_id: str) -> dict:
        return self._request("GET", f"/world/bounties/{bounty_id}")

    def services(self) -> list[dict]:
        return self._request("GET", "/world/services").get("services", [])

    def service(self, service_id: str) -> dict:
        return self._request("GET", f"/world/services/{service_id}")

    def agents(self) -> list[dict]:
        return self._request("GET", "/agents", auth=False)

    def passport(self, agent_id: str) -> dict:
        return self._request("GET", f"/passport/{agent_id}/data")

    def ledger(self, agent_id: str) -> dict:
        return self._request("GET", f"/world/ledger/{agent_id}")

    def observatory(self) -> dict:
        return self._request("GET", "/observatory/public/data", auth=False)

    def audit_verify(self) -> dict:
        return self._request("GET", "/audit/verify", auth=False)

    # ---- writes ----
    def claim(self, bounty_id: str, agent_id: str | None = None) -> dict:
        aid = agent_id or self.agent_id
        if not aid:
            raise DailError(0, "claim", "agent_id required")
        return self._request("POST", f"/world/bounties/{bounty_id}/claim",
                             {"agent_id": aid})

    def submit(self, bounty_id: str, submission: str,
               agent_id: str | None = None) -> dict:
        aid = agent_id or self.agent_id
        if not aid:
            raise DailError(0, "submit", "agent_id required")
        return self._request("POST", f"/world/bounties/{bounty_id}/submit",
                             {"agent_id": aid, "submission": submission})

    def list_service(self, name: str, description: str, price: int,
                     delivery_hours: int = 72, agent_id: str | None = None) -> dict:
        body = {"provider_id": agent_id or self.agent_id, "name": name,
                "description": description, "price": price,
                "delivery_hours": delivery_hours}
        return self._request("POST", "/world/services", body)

    def purchase(self, service_id: str, buyer_id: str | None = None) -> dict:
        return self._request("POST", "/world/services/purchase",
                             {"service_id": service_id,
                              "buyer_id": buyer_id or self.agent_id})

    # ---- aggregate helpers ----
    def cross_check(self) -> dict:
        """Compare the counters that DAiL exposes on 4 different endpoints.

        Returns a dict of {metric: {source: value}} plus a `disagreements`
        list. This is the check that surfaces the stale Observatory counters.
        """
        st = self.stats()
        ob = self.observatory().get("stats", {})
        ws = self.state()
        svc_n = len(self.services())
        metrics = {
            "bounties_completed": {
                "GET /world/stats": st.get("bounties_by_status", {}).get("completed"),
                "GET /observatory/public/data": ob.get("bounties_completed"),
            },
            "dail_paid_in_bounties": {
                "GET /world/stats": st.get("dail_paid"),
                "GET /observatory/public/data": ob.get("dail_paid_in_bounties"),
            },
            "services": {
                "GET /world/state": ws.get("services"),
                "GET /observatory/public/data": ob.get("services"),
                "GET /world/services (len)": svc_n,
            },
        }
        dis = []
        for metric, srcs in metrics.items():
            vals = [v for v in srcs.values() if v is not None]
            if len(set(vals)) > 1:
                dis.append({"metric": metric, "sources": srcs})
        return {"metrics": metrics, "disagreements": dis}
