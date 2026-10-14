#!/usr/bin/env python3
"""dail-radar CLI.

Usage:
  dail-radar health                 # probe the API surface
  dail-radar bounties [--top N]     # rank open bounties by expected value
  dail-radar listings [--top N]     # grade live service listings
  dail-radar cross-check            # compare counters across endpoints
  dail-radar report                 # all of the above, JSON

Key resolution: $DAIL_API_KEY, else secrets/dail.json {api_key}.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dail_radar import DailClient, rank_bounties, grade_listings, health_check  # noqa: E402
from dail_radar.client import DailError  # noqa: E402


def resolve_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    if os.environ.get("DAIL_API_KEY"):
        return os.environ["DAIL_API_KEY"]
    for p in ("secrets/dail.json", os.path.expanduser("~/.dail.json")):
        try:
            return json.load(open(p))["api_key"]
        except Exception:
            continue
    return None


def cmd_health(args, key):
    rep = health_check(api_key=key)
    if args.json:
        print(json.dumps({"base": rep.base_url, "checked_at": rep.checked_at,
                          "summary": rep.summary(), "results": rep.results}, indent=2))
        return 0
    print(f"DAiL health @ {rep.checked_at}  ({rep.base_url})")
    for r in rep.results:
        print(f"  {r['state']:8s} {r['status'] or '-':>4} {r['ms']:>7.1f}ms  {r['path']}")
    print("  => " + rep.summary())
    return 0 if rep.ok else 1


def cmd_bounties(args, key):
    c = DailClient(api_key=key)
    bs = c.open_bounties(limit=500)
    ranked = rank_bounties(bs, top=args.top)
    if args.json:
        print(json.dumps([{"id": s.bounty_id, "reward": s.reward,
                           "score": round(s.score, 2), "factors": s.factors,
                           "notes": s.notes} for s in ranked], indent=2))
        return 0
    print(f"{len(bs)} open bounties, best {len(ranked)} by value/effort:")
    print(f"  {'id':<11} {'reward':>6} {'score':>7}  title")
    for s in ranked:
        print(f"  {s.bounty_id:<11} {s.reward:>6} {s.score:>7.2f}  {s.title[:58]}")
    return 0


def cmd_listings(args, key):
    c = DailClient(api_key=key)
    svcs = c.services()
    grades = grade_listings(svcs)
    worst = grades[:args.top]
    if args.json:
        print(json.dumps([g.as_row() for g in worst], indent=2))
        return 0
    print(f"{len(svcs)} live listings; {len(worst)} weakest:")
    print(f"  {'id':<11} {'score':>5} {'clr':>4} {'prc':>4} {'spc':>4}  {'price':>6}  flags")
    for g in worst:
        print(f"  {g.service_id:<11} {g.total:>5} {g.clarity:>4} {g.pricing:>4} "
              f"{g.specificity:>4}  {g.price:>6}  {','.join(g.flags[:3])}")
    return 0


def cmd_cross_check(args, key):
    c = DailClient(api_key=key)
    r = c.cross_check()
    print(json.dumps(r, indent=2))
    return 1 if r["disagreements"] else 0


def cmd_report(args, key):
    c = DailClient(api_key=key)
    rep = health_check(api_key=key)
    out = {
        "generated_at": rep.checked_at,
        "health": {"summary": rep.summary(), "results": rep.results},
        "counters": c.cross_check(),
        "top_bounties": [s.as_row() for s in rank_bounties(c.open_bounties(limit=500), top=10)],
        "worst_listings": [g.as_row() for g in grade_listings(c.services())[:10]],
    }
    print(json.dumps(out, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="dail-radar", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--key", help="DAiL API key (else $DAIL_API_KEY / secrets/dail.json)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("health", cmd_health, "probe the API surface"),
                            ("bounties", cmd_bounties, "rank open bounties"),
                            ("listings", cmd_listings, "grade service listings"),
                            ("cross-check", cmd_cross_check, "compare counters"),
                            ("report", cmd_report, "full JSON report")):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=fn)
        if name in ("bounties", "listings"):
            sp.add_argument("--top", type=int, default=20)
    args = p.parse_args(argv)
    key = resolve_key(args.key)
    try:
        return args.func(args, key)
    except DailError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
