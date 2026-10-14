"""Bounty scoring: rank open bounties by expected value per unit of effort.

The signal is deliberately simple and explainable. Each factor is a small
number with a documented reason, so a hunter can see *why* a bounty ranked
where it did.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ScoreBreakdown:
    bounty_id: str
    title: str
    reward: int
    score: float
    factors: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def as_row(self) -> dict:
        return {"id": self.bounty_id, "reward": self.reward,
                "score": round(self.score, 2), "title": self.title[:60]}


# Heuristic effort cost by keyword. Lower = cheaper to complete.
_CHEAP = ("micro", "daily", "roast", "review", "audit", "spec", "docs",
          "guide", "testimonial", "localize", "list")
_DEAR = ("build", "challenge", "solve", "squad", "superagent", "milestone",
         "real-money", "stripe", "webhook", "video", "explainer")


def _effort(title: str, description: str) -> tuple[float, str]:
    """Return (ease, reason). ease = fraction of a bounty's reward a hunter
    can realistically convert: 1.0 light, 0.85 default, 0.5 heavy."""
    t = (title + " " + description).lower()
    if any(k in t for k in _DEAR):
        return 0.5, "heavy keyword (build/challenge/integration)"
    if any(k in t for k in _CHEAP):
        return 1.0, "light keyword (review/audit/spec/docs)"
    return 0.85, "unclassified"


def score_bounty(bounty: dict, *, competition: int = 0,
                 poster_is_house: bool | None = None) -> ScoreBreakdown:
    """Score a single bounty dict (as returned by GET /world/bounties).

    score = reward * ease * house_factor * competition_factor

    - reward: the DAIL payout (int).
    - ease: 1.0 light, 0.85 default, 0.5 heavy (a heavy bounty is worth less
      per unit of effort, so it is discounted).
    - house_factor: 1.0 for house-posted (reliably reviewed), 0.9 otherwise.
    - competition_factor: 1/(1+competition*0.15) — each rival hunter costs ~15%.
    """
    bid = bounty.get("id", "?")
    title = bounty.get("title", "")
    desc = bounty.get("description", "") or ""
    reward = int(bounty.get("reward") or 0)
    poster = bounty.get("poster_id", "")
    if poster_is_house is None:
        poster_is_house = poster in ("dail_host", "dail_manager")

    effort, why = _effort(title, desc)
    house = 1.0 if poster_is_house else 0.9
    comp = 1.0 / (1.0 + competition * 0.15)
    score = reward * effort * house * comp

    notes = [why]
    if reward <= 5:
        notes.append("low reward — cheap but low absolute value")
    if len(desc) < 60:
        notes.append("thin description — scope risk")
    if bounty.get("work_window_hours", 0) and bounty["work_window_hours"] <= 24:
        notes.append("short work window")

    return ScoreBreakdown(
        bounty_id=bid, title=title, reward=reward, score=score,
        factors={"reward": reward, "ease": effort, "house_factor": house,
                 "competition_factor": round(comp, 3), "competition": competition},
        notes=notes)


def rank_bounties(bounties: Iterable[dict], *, top: int | None = None) -> list[ScoreBreakdown]:
    """Score and sort bounties best-first."""
    scored = [score_bounty(b) for b in bounties]
    scored.sort(key=lambda s: (-s.score, -s.reward, s.bounty_id))
    return scored[:top] if top else scored
