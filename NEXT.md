# Next actions

Ordered task queue. `PLAN.md` says *what* and *why*; this file says *what to do
next* and *when it is done*.

Rule: do not skip ahead. Each item has a definition of done — if you cannot say
"done because X", it is not done.

---

## Now — before any code (~45 min total)

### 1. JSON-LD probe
Fetch one GPU product page from each store and check whether it publishes
structured data with a price and an identifier.

- `x-kom.pl` — any product URL from `sitemap-products-*.xml`
- `morele.net` — any GPU product URL

Look for: `application/ld+json`, `"@type": "Product"`, `"price"`,
`"availability"`, `"gtin13"`, `"mpn"`, `"sku"`.

**Done when:** a yes/no per store is recorded in `PLAN.md` §11 and §14, with the
field names actually found.

**Why first:** if `gtin13` is present at both stores, the matching layer (§6)
becomes close to a join instead of a matcher, which changes the key used in
item 3 and the whole shape of P2. Fifteen minutes here can save a week later.

### 2. Ceneo terms + written answer
Read the regulamin for the two clauses that matter — storing/displaying Ceneo
data outside links and wishlists, and any restriction on competing comparison
services — then email `partnerzy@ceneo.pl` with the same questions so the answer
is in writing.

**Done when:** a reply exists and its constraints are summarised in `PLAN.md` §9.

---

## P1 — prove the model by hand (this week)

No scraper. No automation. The point is to find out whether the ranking is any
good before building a pipe for it.

### 3. `data/gpus.csv` — 40–60 rows
One row per `chip + vram_gb`. Minimum columns:

```
chip, vram_gb, generation, perf_1440_raster, perf_1440_rt, vram_score,
tdp_w, length_mm, msrp_pln, notes
```

**Done when:** every row carries a performance number *and* a note saying how it
was derived (spec proxy formula, or source). No unexplained magic numbers.

### 4. `data/overrides.yaml`
Stub file plus the per-store matching rules you discover while filling in item 5.

**Done when:** it exists and at least the first five awkward AIB titles are
mapped by hand.

### 5. Manual price pass
Two stores, every chip, prices fetched by hand and timestamped.

**Done when:** every chip has at least one credible offer (in stock, first-party,
new, not a bundle), and `p_buy` / `p_ref` can be computed for all of them.

### 6. `build.py` + templates
Jinja2 → `dist/index.html` (leaderboard) + `dist/gpu/<slug>.html` (one per chip).
Sorting is ~30 lines of vanilla JS.

**Done when:** the site renders locally and a human reads it and disagrees with
at least one placement. Disagreement is the signal that the model is legible.

### 7. Deploy
`wrangler pages deploy dist` → `<project>.pages.dev`.

**Done when:** the URL loads on a phone and the footer shows the price timestamp.

### 8. `/metodologia/` page
The filter list, the perf formula, the data vintage.

**Done when:** published. Write this *before* defending the product — it is the
trust moat and it costs an hour.

---

## Gate before P2

**Ship P1 and wait two weeks.** If nobody uses it, argues with it, or links to
it, **stop**. Do not build the scraper. The model was the bet, and it lost
cheaply.

Only if P1 gets real use does the sequence continue.

---

## P2 — automate the pipe (only after the gate)

### 9. `scrape.py`
Two stores, the SKUs from item 3, writing `data/prices.json` and appending to
`data/history.jsonl`. `p_buy` computed by the §3 filter list, never hand-edited.

**Done when:** it runs green three times in a row and produces prices that match
a manual spot-check.

### 10. Schedule + deploy hook
systemd timer (a few times a day, `Persistent=true`, `RandomizedDelaySec`), build-time
staleness guard, dead-man's switch ping.

**Done when:** prices refresh unattended for two weeks without a manual touch.

---

## P3 — turn on the money

### 11. Ceneo PID wiring
PID on every offer link, **distinct sub-ID per page/placement**,
`rel="sponsored nofollow noopener"`, visible disclosure.

**Done when:** a click on a GPU page appears in the Ceneo panel against the
correct sub-ID.

---

## Deliberately not next

Writing these down so future-you does not start them early:

| Not now | Because |
|---|---|
| Pages per AIB model | thin near-duplicate content, no search demand |
| More stores (MediaExpert, MediaMarkt) | ~10% of value for ~80% of maintenance |
| Allegro / OLX / used market | different risk model, separate product |
| Database (Postgres/SQLite) | 10 MB/year does not need one |
| Price history + alerts | needs P2 data first; commodity anyway |
| Own benchmark suite | expensive; spec proxy is enough to test demand |
| Workers/ad-serving | nothing to serve yet |

---

## Definition of done for v1

A stranger lands on the page from search, understands which card to buy for
their budget, clicks through to a store, and the price they see is not stale.
Everything else is optimisation.
