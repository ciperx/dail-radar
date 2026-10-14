"""DAiL Radar — a zero-dependency toolkit for participants in the DAiL agent marketplace.

Public API:
    from dail_radar import DailClient, score_bounty, ListingGrader, health_check
"""
from .client import DailClient, DailError
from .score import score_bounty, rank_bounties, ScoreBreakdown
from .listings import ListingGrader, grade_listings
from .health import health_check, HealthReport

__version__ = "0.1.0"
__all__ = [
    "DailClient", "DailError",
    "score_bounty", "rank_bounties", "ScoreBreakdown",
    "ListingGrader", "grade_listings",
    "health_check", "HealthReport",
]
