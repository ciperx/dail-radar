"""Offline tests for dail_radar. No network required.

Run: python -m pytest tests/ -q      (or: python tests/test_offline.py)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dail_radar import rank_bounties, grade_listings, score_bounty  # noqa: E402
from dail_radar.listings import ListingGrader  # noqa: E402


# ---- bounty scoring ----

def test_light_heavy_ordering():
    light = {"id": "b1", "title": "Micro review", "description": "review it " * 12,
             "reward": 10, "poster_id": "dail_host"}
    heavy = {"id": "b2", "title": "BUILD CHALLENGE project", "description": "build " * 12,
             "reward": 10, "poster_id": "dail_host"}
    assert score_bounty(light).score > score_bounty(heavy).score


def test_reward_scales_score():
    a = {"id": "a", "title": "audit", "description": "x" * 80, "reward": 5, "poster_id": "dail_host"}
    b = {"id": "b", "title": "audit", "description": "x" * 80, "reward": 20, "poster_id": "dail_host"}
    assert score_bounty(b).score == 4 * score_bounty(a).score


def test_competition_lowers_score():
    b = {"id": "b", "title": "audit", "description": "x" * 80, "reward": 10, "poster_id": "dail_host"}
    assert score_bounty(b, competition=3).score < score_bounty(b, competition=0).score


def test_non_house_discounted():
    h = {"id": "h", "title": "audit", "description": "x" * 80, "reward": 10, "poster_id": "dail_host"}
    n = dict(h, poster_id="random_agent")
    assert score_bounty(h).score > score_bounty(n).score


def test_rank_sorted_desc():
    bs = [{"id": str(i), "title": "audit review", "description": "x" * 80,
           "reward": r, "poster_id": "dail_host"} for i, r in enumerate([1, 50, 7])]
    ranked = rank_bounties(bs)
    assert [s.reward for s in ranked] == [50, 7, 1]


def test_rank_top_caps():
    bs = [{"id": str(i), "title": "audit", "description": "x" * 80,
           "reward": i + 1, "poster_id": "dail_host"} for i in range(30)]
    assert len(rank_bounties(bs, top=5)) == 5


# ---- listing grader ----

def test_good_listing_scores_high():
    svc = {"id": "s1", "provider_id": "p", "price": 10,
           "name": "Sourced research brief",
           "description": "A 500-word brief in JSON and Markdown, every claim "
                          "traceable to a public source, delivered in 24h with a README.",
           "delivery_hours": 24}
    assert ListingGrader().grade(svc).total >= 70


def test_placeholder_listing_scores_low():
    svc = {"id": "s2", "provider_id": "p", "price": 1, "name": "x",
           "description": "z", "delivery_hours": 72}
    g = ListingGrader().grade(svc)
    assert g.total < 40
    assert "placeholder_description" in g.flags or "name_too_short" in g.flags


def test_nonpositive_price_flagged():
    svc = {"id": "s3", "provider_id": "p", "price": 0, "name": "edge case service",
           "description": "a reasonably long description " * 5, "delivery_hours": 24}
    g = ListingGrader().grade(svc)
    assert "nonpositive_price" in g.flags
    assert g.pricing <= 5


def test_absurd_price_flagged():
    svc = {"id": "s4", "provider_id": "p", "price": 99999999999999999999,
           "name": "bounds", "description": "z", "delivery_hours": 72}
    g = ListingGrader().grade(svc)
    assert "price_above_ceiling" in g.flags


def test_trial_above_price_flagged():
    svc = {"id": "s5", "provider_id": "p", "price": 10, "trial_price": 100,
           "name": "Trial service", "description": "d" * 150, "delivery_hours": 24}
    g = ListingGrader().grade(svc)
    assert "trial_above_price" in g.flags


def test_grade_listings_sorted_worst_first():
    good = {"id": "g", "provider_id": "p", "price": 10, "name": "Good service name",
            "description": "json csv report README sources " * 6, "delivery_hours": 24}
    bad = {"id": "b", "provider_id": "p", "price": 0, "name": "x",
           "description": "z", "delivery_hours": 72}
    out = grade_listings([good, bad])
    assert out[0].service_id == "b"


def test_grader_is_deterministic():
    svc = {"id": "s", "provider_id": "p", "price": 5, "name": "Service name here",
           "description": "deliverable text " * 8, "delivery_hours": 24}
    a = ListingGrader().grade(svc)
    b = ListingGrader().grade(svc)
    assert (a.total, a.clarity, a.pricing, a.specificity) == \
           (b.total, b.clarity, b.pricing, b.specificity)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL ", name, e)
    print(("\n%d failure(s)" % fails) if fails else "\nall tests passed")
    raise SystemExit(1 if fails else 0)
