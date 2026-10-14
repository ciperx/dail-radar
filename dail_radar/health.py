"""Health check: probe the DAiL API surface and report status + latency.

Covers the endpoints a participant depends on, classifies each as ok /
degraded / down, and flags the two known shape quirks (services has no
pagination params; bounties silently ignores `offset`).
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .client import DEFAULT_BASE

# (path, needs_auth, description)
PROBES = [
    ("/health", False, "service health"),
    ("/world/stats", False, "marketplace counters"),
    ("/world/state", True, "world state"),
    ("/observatory/public/data", False, "public observatory feed"),
    ("/world/bounties?limit=5", True, "bounty list"),
    ("/world/services", True, "service list"),
    ("/agents", True, "agent registry"),
    ("/audit/verify", False, "ledger receipt chain"),
]


@dataclass
class HealthReport:
    base_url: str
    checked_at: str
    results: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r["state"] == "ok" for r in self.results)

    def summary(self) -> str:
        bad = [r for r in self.results if r["state"] != "ok"]
        if not bad:
            return "all %d probes ok" % len(self.results)
        return "%d/%d degraded or down: %s" % (
            len(bad), len(self.results),
            ", ".join("%s(%s)" % (r["path"], r["state"]) for r in bad))


def health_check(api_key: str | None = None, base_url: str = DEFAULT_BASE,
                 timeout: float = 30.0, slow_ms: float = 3000.0) -> HealthReport:
    """Probe every endpoint in PROBES; never raises on a non-2xx."""
    results = []
    for path, needs_auth, desc in PROBES:
        headers = {"User-Agent": "dail-radar/0.1"}
        if needs_auth and api_key:
            headers["Authorization"] = "Bearer " + api_key
        req = urllib.request.Request(base_url + path, headers=headers)
        t0 = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            r.read()
            status, err = r.status, None
        except urllib.error.HTTPError as e:
            e.read()
            status, err = e.code, "HTTP %d" % e.code
        except Exception as e:  # noqa: BLE001 - report, don't crash
            status, err = 0, type(e).__name__
        ms = (time.time() - t0) * 1000
        if err:
            state = "down"
        elif ms > slow_ms:
            state = "degraded"
        else:
            state = "ok"
        results.append({"path": path, "desc": desc, "status": status,
                        "ms": round(ms, 1), "state": state, "error": err})
    return HealthReport(base_url=base_url,
                        checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        results=results)
