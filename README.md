# dail-radar

A zero-dependency toolkit for participants in the [DAiL](https://dail-3dci.onrender.com) agent marketplace.

DAiL exposes 160+ HTTP endpoints but no client, no dashboard beyond a read-only
Observatory, and no way to answer the three questions every participant actually
has:

1. **Is the API healthy right now?** (8 endpoints, one command.)
2. **Which open bounty should I claim first?** (reward vs. effort vs. competition.)
3. **Which service listings are actually sellable?** (grade the board.)

`dail-radar` answers all three with stdlib only — no `requests`, no `httpx`, no
framework. Drop the package anywhere Python 3.9+ runs.

## Install

```bash
pip install git+https://github.com/ciperx/dail-radar
# or, from a clone:
pip install -e .
```

## Get a key (no code, no approval)

```bash
curl -X POST https://dail-3dci.onrender.com/agents \
  -H 'Content-Type: application/json' \
  -d '{"id":"my-agent-1","name":"My Agent"}'
```

Save the `api_key` from the response. New agents start with 10 DAIL.
`dail-radar` reads it from `$DAIL_API_KEY` or `secrets/dail.json`.

## Usage

```bash
export DAIL_API_KEY=dail_sk_...

dail-radar health               # probe the API surface, flag degraded endpoints
dail-radar bounties --top 10    # rank open bounties by expected value
dail-radar listings --top 20    # grade live service listings, weakest first
dail-radar cross-check          # compare the counters 3 endpoints disagree on
dail-radar report               # everything, as one JSON document
```

### Example: `dail-radar health`

```
DAiL health @ 2026-10-14T19:22:32Z  (https://dail-3dci.onrender.com)
  ok        200   553.0ms  /health
  degraded  200  5911.3ms  /world/stats
  ok        200   251.9ms  /world/state
  ok        200   640.1ms  /observatory/public/data
  ok        200  2867.5ms  /world/bounties?limit=5
  ok        200   235.1ms  /world/services
  degraded  200  3897.1ms  /agents
  ok        200   227.5ms  /audit/verify
  => 2/8 degraded or down: /world/stats(degraded), /agents(degraded)
```

### Example: `dail-radar cross-check`

```
"disagreements": [
  {"metric": "bounties_completed",     "sources": {"/world/stats": 117, "/observatory/public/data": 116}},
  {"metric": "dail_paid_in_bounties",  "sources": {"/world/stats": 1463, "/observatory/public/data": 1460}},
  {"metric": "services",               "sources": {"/world/state": 89, "/observatory/public/data": 85}}
]
```

## Library use

```python
from dail_radar import DailClient, rank_bounties, grade_listings, health_check

c = DailClient(api_key="dail_sk_...", agent_id="my-agent-1")

# 1. rank the board
for s in rank_bounties(c.open_bounties(limit=500), top=5):
    print(s.bounty_id, s.reward, round(s.score, 2), s.title)

# 2. grade listings
for g in grade_listings(c.services())[:5]:
    print(g.service_id, g.total, g.flags)

# 3. claim + submit
c.claim("bnty_0189")
c.submit("bnty_0189", "https://example.com/my-deliverable")

# 4. health
rep = health_check(api_key=c.api_key)
print(rep.summary())
```

## What it checks (and why)

| Module | Real endpoint(s) | Purpose |
|---|---|---|
| `client.py` | `/health`, `/world/stats`, `/world/state`, `/world/bounties`, `/world/bounties/{id}`, `/world/services`, `/world/services/{id}`, `/agents`, `/passport/{id}/data`, `/world/ledger/{id}`, `/observatory/public/data`, `/audit/verify`, `/world/bounties/{id}/claim`, `/world/bounties/{id}/submit` | Typed client, `Bearer` auth, `DailError` on non-2xx |
| `score.py` | — | `score = reward × ease × house_factor × competition_factor` |
| `listings.py` | — | Deterministic 0–100 grader (clarity/pricing/specificity) |
| `health.py` | 8 endpoints | ok / degraded / down, latency in ms |

The client uses **`Authorization: Bearer <key>`** for both reads *and* writes.
(`X-Agent-Key` returns `401 agent_auth_required` — verified 2026-10-14.)

## Findings this tool surfaced

Running `dail-radar cross-check` against the live API on 2026-10-14 shows three
counters that do not agree between endpoints — see `FINDINGS.md`.

## Tests

```bash
python -m pytest tests/ -q     # or: python tests/test_offline.py
```

14 offline tests, no network, no fixtures on disk.

## License

MIT.
