"""Service listing grader: score a listing 0-100 on the three axes the
marketplace actually cares about — description clarity, pricing sanity,
deliverable specificity.

Built for the `Service listing quality review (20)` style of work, but usable
by any seller as a pre-flight check before publishing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Words that signal a concrete, checkable deliverable.
_SPECIFIC = ("json", "csv", "svg", "html", "markdown", "report", "source",
             "readme", "test", "tests", "poc", "spec", "endpoint", "url",
             "citation", "sources", "word", "words", "page", "pages", "mp4",
             "png", "yaml", "openapi", "screenshot", "table", "list", "code")
# Words that signal an unclear or placeholder listing.
_VAGUE = ("misc", "various", "stuff", "things", "as needed", "tbd", "test",
          "probe", "not for sale", "x", "z", "self purchase", "temporary")


@dataclass
class Grade:
    service_id: str
    name: str
    provider_id: str
    price: int
    total: int
    clarity: int
    pricing: int
    specificity: int
    flags: list = field(default_factory=list)
    fixes: list = field(default_factory=list)

    def as_row(self) -> dict:
        return {"id": self.service_id, "provider": self.provider_id,
                "price": self.price, "total": self.total,
                "clarity": self.clarity, "pricing": self.pricing,
                "specificity": self.specificity, "flags": self.flags}


class ListingGrader:
    """Deterministic 0-100 grader. No network, no LLM, reproducible."""

    def __init__(self, price_floor: int = 1, price_ceil: int = 200):
        self.price_floor = price_floor
        self.price_ceil = price_ceil

    def grade(self, svc: dict) -> Grade:
        sid = svc.get("id", "?")
        name = svc.get("name", "") or ""
        desc = svc.get("description", "") or ""
        price = int(svc.get("price") or 0)
        flags, fixes = [], []

        # --- clarity (0-40): name + description length and vagueness ---
        clarity = 0
        if 4 <= len(name) <= 80:
            clarity += 10
        elif len(name) > 80:
            clarity += 4
            flags.append("name_too_long")
            fixes.append("Trim the service name to <=80 chars.")
        else:
            flags.append("name_too_short")
            fixes.append("Give the service a descriptive name (>=4 chars).")
        dl = len(desc)
        if dl >= 120:
            clarity += 30
        elif dl >= 60:
            clarity += 20
            fixes.append("Expand the description to >=120 chars: what you deliver, turnaround, format.")
        elif dl >= 20:
            clarity += 10
            flags.append("thin_description")
            fixes.append("Description is under 60 chars — add deliverable, format and turnaround.")
        else:
            flags.append("placeholder_description")
            fixes.append("Description looks like a placeholder; write a real one.")
        low = (name + " " + desc).lower()
        vague_hits = [v for v in _VAGUE if v in low and len(desc) < 120]
        if vague_hits:
            clarity = max(0, clarity - 8)
            flags.append("vague_terms:" + ",".join(vague_hits[:3]))
            fixes.append("Replace vague terms (%s) with a concrete deliverable." % ", ".join(vague_hits[:3]))

        # --- pricing (0-30) ---
        pricing = 30
        if price <= 0:
            pricing = 5
            flags.append("nonpositive_price")
            fixes.append("Price must be >=1 DAIL to be a real offer.")
        elif price > self.price_ceil:
            pricing = 8
            flags.append("price_above_ceiling")
            fixes.append("Price %d is far above the board's working range; justify it or lower it." % price)
        elif price > 50:
            pricing = 20
            flags.append("price_premium")
            fixes.append("Premium price: add scope/outcome detail to justify %d DAIL." % price)
        if svc.get("trial_price") is not None:
            tp = svc["trial_price"]
            if tp > price:
                pricing = max(0, pricing - 10)
                flags.append("trial_above_price")
                fixes.append("Trial price (%d) exceeds list price (%d)." % (tp, price))

        # --- specificity (0-30) ---
        hits = [w for w in _SPECIFIC if w in low]
        specificity = min(30, len(hits) * 6)
        if not hits:
            flags.append("no_concrete_deliverable")
            fixes.append("Name the exact artifact (e.g. 'JSON', 'README', '10-page report').")
        if svc.get("delivery_hours") and svc["delivery_hours"] > 72:
            specificity = max(0, specificity - 5)
            flags.append("slow_delivery")
            fixes.append("Delivery >72h; state why or tighten it.")

        total = max(0, min(100, clarity + pricing + specificity))
        return Grade(service_id=sid, name=name, provider_id=svc.get("provider_id", ""),
                     price=price, total=total, clarity=clarity, pricing=pricing,
                     specificity=specificity, flags=flags, fixes=fixes)


def grade_listings(services: Iterable[dict], *, price_floor: int = 1,
                   price_ceil: int = 200) -> list[Grade]:
    g = ListingGrader(price_floor, price_ceil)
    out = [g.grade(s) for s in services]
    out.sort(key=lambda x: (x.total, x.service_id))
    return out
