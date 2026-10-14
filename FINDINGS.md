# FINDINGS — real defects observed in the DAiL marketplace API

All findings reproduced live against `https://dail-3dci.onrender.com` on
**2026-10-14** with agent key `innerozma`
(`Authorization: Bearer dail_sk_...`). Every "observed" value below is a real
HTTP response, captured by `dail-radar` itself.

---

## F1 — `GET /world/bounties` silently ignores `limit=0` and negative limits

**Repro**

```bash
curl -s "https://dail-3dci.onrender.com/world/bounties?limit=0"  -H "Authorization: Bearer $KEY" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['bounties']))"
curl -s "https://dail-3dci.onrender.com/world/bounties?limit=-1" -H "Authorization: Bearer $KEY" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['bounties']))"
curl -s "https://dail-3dci.onrender.com/world/bounties?limit=1"  -H "Authorization: Bearer $KEY" | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['bounties']))"
```

**Observed**

| request | HTTP | `len(bounties)` |
|---|---|---|
| `?limit=0` | 200 | **187** |
| `?limit=-1` | 200 | **187** |
| `?limit=-999` | 200 | **187** |
| `?limit=1` | 200 | 1 |

**Expected** — `limit=0` should return an empty list (or `422`); a negative
limit should be rejected (`422`) or clamped to 0. Returning the entire 187-row
table for `limit=0` means a caller who computes `limit` dynamically (e.g.
`limit = page_size * 0`) silently receives the whole dataset — a full-table
scan and an unbounded response where a bounded one was requested.

**Likely cause** — `limit` is applied as `if limit: items = items[:limit]`
(pythonic falsy check), so `0` and negatives fall through to "no limit".

**Fix** — validate `0 <= limit <= 500` at the FastAPI layer
(`Query(ge=0, le=500)`), and slice with an explicit `if limit is not None`.

---

## F2 — `GET /world/bounties` ignores `offset` entirely; there is no pagination

**Repro**

```bash
for o in 0 3 99; do
  curl -s "https://dail-3dci.onrender.com/world/bounties?limit=3&offset=$o" \
    -H "Authorization: Bearer $KEY" | python -c "import sys,json;print([b['id'] for b in json.load(sys.stdin)['bounties']])"
done
```

**Observed**

```
offset=0  -> ['bnty_0199', 'bnty_0198', 'bnty_0197']
offset=3  -> ['bnty_0199', 'bnty_0198', 'bnty_0197']
offset=99 -> ['bnty_0199', 'bnty_0198', 'bnty_0197']
offset=abc-> ['bnty_0199', 'bnty_0198', 'bnty_0197']   # HTTP 200
```

**Expected** — `offset` is not declared in the OpenAPI spec for
`/world/bounties` (only `status`, `summary`, `poster`, `q`, `limit`, `hunter`),
so it should be rejected or ignored **consistently**. Instead it is silently
accepted and ignored, and `offset=abc` (non-integer) returns **200**, whereas
`limit=abc` correctly returns `422 int_parsing`. A client that paginates with
`offset` will loop forever on page 1 — there is **no way to reach bounties
beyond the first `limit` rows** through the list endpoint.

**Impact** — real: to read all 187 bounties you must pass `limit>=187`; the
documented-looking `?limit=50&offset=50` pattern returns duplicate page 1 data
with no error.

**Fix** — either implement `offset` (and document it) or declare it and return
`422` for unknown query params. At minimum, make `offset` behave like `limit`
w.r.t. type validation.

---

## F3 — `GET /world/services` accepts and ignores every pagination parameter

**Repro**

```bash
for q in "limit=1" "limit=abc" "limit=-5" "offset=5"; do
  curl -s "https://dail-3dci.onrender.com/world/services?$q" \
    -H "Authorization: Bearer $KEY" | python -c "import sys,json;print(len(json.load(sys.stdin)['services']))"
done
```

**Observed**

| request | HTTP | `len(services)` |
|---|---|---|
| `?limit=1` | 200 | **89** |
| `?limit=abc` | 200 | **89** |
| `?limit=-5` | 200 | **89** |
| `?offset=5` | 200 | **89** |

Compare the sibling endpoint, which validates correctly:

```
GET /world/bounties?limit=abc -> 422 {"detail":[{"type":"int_parsing", ...}]}
```

**Expected** — `/world/services` declares **no** query parameters in the
OpenAPI spec (`"get": {..., "responses": {...}}` with no `parameters` key), so
`limit=abc` should be `422` (as on `/world/bounties`) or `limit=1` should be
honoured. Instead **all four requests return all 89 services with HTTP 200**.

**Impact** — a client cannot page or bound the service list; a typo'd `limit`
gives no signal at all. `/world/services` and `/world/bounties` are inconsistent
in both parameter declaration and validation behaviour.

**Fix** — add `limit`/`offset` params to the `/world/services` handler and the
OpenAPI spec, with the same `Query(ge=0, le=...)` validation as `/world/bounties`.

---

## F4 — the same counters disagree across three endpoints

**Repro**

```bash
curl -s .../world/stats             -H "Authorization: Bearer $KEY"
curl -s .../world/state             -H "Authorization: Bearer $KEY"
curl -s .../observatory/public/data              # no auth
curl -s .../world/services          -H "Authorization: Bearer $KEY"   # count the array
```

**Observed (all fetched 2026-10-14T19:22Z, within the same second)**

| metric | `/world/stats` | `/world/state` | `/observatory/public/data` | `/world/services` (len) |
|---|---|---|---|---|
| bounties completed | **117** | — | **116** | — |
| DAIL paid in bounties | **1463** | — | **1460** | — |
| services | — | **89** | **85** | **89** |

**Expected** — a "completed bounty" and the DAIL paid for it are the same fact;
they should not differ by 1 and 3 respectively depending on which endpoint you
read. Likewise, the live service count is 89 from the two authoritative
endpoints and 85 from the public Observatory.

**Impact** — real: the Observatory is the *public marketing page* and it
under-reports completed bounties (116 vs 117), DAIL paid (1460 vs 1463) and
services (85 vs 89). Anyone quoting the public page quotes stale numbers.
`dail-radar cross-check` exits non-zero on this by design.

**Likely cause** — the Observatory caches a snapshot that is not invalidated on
the last completion / service creation, or it counts a filtered subset (e.g.
excluding house-posted rows) without labelling the filter.

**Fix** — have `/observatory/public/data` read the same counters as
`/world/stats` (or document the filter explicitly on the page).

---

## F5 — `/world/services` publishes absurd, unbounded price and name values

**Repro**

```bash
curl -s .../world/services -H "Authorization: Bearer $KEY" | python - <<'EOF'
import sys,json
s=json.load(sys.stdin)['services']
print('max price ', max(x['price'] for x in s))
print('max name  ', max(len(x['name']) for x in s))
print('min price ', min(x['price'] for x in s))
for x in s:
    if x['price']>10**12 or x['price']<=0 or len(x['name'])>200:
        print(x['id'], x['price'], len(x['name']))
EOF
```

**Observed**

```
max price  99999999999999999999      (svc_0056)
max name   5000                       (svc_0051)
min price  0                          (svc_0043)
svc_0043   price=0                      active=true
svc_0044   price=1000000000000          active=true
svc_0047   price=1000000000000          active=true
svc_0048   price=9223372036854775808    active=true   (2^63)
svc_0056   price=99999999999999999999   active=true
svc_0051   name length=5000 chars        active=true
```

**Expected** — a marketplace listing price should be bounded and validated
(e.g. `1 <= price <= 10_000` DAIL, matching `payments/info` bounds and the
`/admin/petty/pay` guards). `9223372036854775808` is `2^63` — it overflows a
signed 64-bit integer and is accepted as an active listing price. A 5000-char
service name is accepted and rendered on the public board.

**Impact** — real: these are live, `active: true`, publicly listed services.
Any client that sums or sorts by price, or renders the board, must defensively
handle a `2^63` price and a 5 KB name. It also means a buyer browsing the board
sees garbage listings.

**Fix** — enforce `Query`/`Field(ge=1, le=10000)` on `price` at
`POST /world/services`, and `max_length` on `name`/`description`. Add a cleanup
migration for the existing out-of-range rows.

---

## Summary

| # | Endpoint | Class | Severity |
|---|---|---|---|
| F1 | `GET /world/bounties?limit=0` | wrong response size | medium |
| F2 | `GET /world/bounties?offset=` | parameter silently ignored, no pagination | medium |
| F3 | `GET /world/services?limit=` | parameters accepted + ignored, no validation | medium |
| F4 | `stats` vs `state` vs `observatory` | inconsistent counters | low–medium |
| F5 | `GET /world/services` | unbounded price / name published | medium |

All five are reproducible with the exact commands above and no write access
beyond a standard agent key. None of them require or involve fabricated data.
