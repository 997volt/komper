# Komper — Plan

**Status:** planning. No implementation.
**Date:** 2026-10-31
**Owner:** 997volt

---

## 1. Thesis

A Polish-language tool that answers one question well:

> **"Which GPU should I buy for my budget, and is this particular offer a good deal?"**

It answers by ranking **performance per złoty** over currently buyable cards,
with a feasibility filter so the recommendation is actually usable, and it
monetises by sending the user to the cheapest credible offer through a Ceneo
affiliate link.

The product is **the model**, not the data collection. Prices are a commodity:
every store, Ceneo, and any competitor can obtain them. The defensible asset is
a transparent performance index plus the judgment layer on top — and that needs
no scraping at all.

### What it is not

| Non-goal | Why |
|---|---|
| A Ceneo competitor on data collection | Ceneo has first-party merchant feeds; scraping to match it is a losing race |
| An affiliate content site | Different business: traffic first, product second; no moat |
| A shop / e-commerce | No stock, no fulfilment, no liability for sales |
| A used-market tracker (v1) | Condition and warranty risk cannot be modelled honestly yet |
| A price *history* product (v1) | History is a commodity Ceneo gives away; cross-sectional value is the wedge |
| A real-time alerting service (v1) | Incompatible with static rebuilds; see §8 |

---

## 2. The unit of the product: three levels

```
chip + VRAM          → the ENTITY. has performance. gets a page. gets ranked.
  └─ AIB model       → an ATTRIBUTE of the offer (cooler, clocks, length, noise)
       └─ offer      → the PRICE. store, url, stock. only this has a price.
```

`RTX 5070 12GB` is the entity. `Gigabyte RTX 5070 Windforce OC 12G` is a variant
of it. `2499 zł at x-kom` is an offer.

**Why rank entities and not AIB SKUs:** within one chip, price varies ~15–30%
across AIB models while performance varies ~1–3% (maybe 5% for aggressive OC
models). Price spreads roughly ten times wider than performance. Ranking AIB
SKUs produces a leaderboard about *which AIB is cheapest*, not about what is a
good buy — and the top of it becomes arbitrage noise from clearances and
marketplace sellers.

**VRAM is part of the key.** `RTX 5060 Ti 8GB` ≠ `RTX 5060 Ti 16GB` — different
price, different 1440p/4K behaviour, different longevity. The canonical key is
`chip + vram_gb`.

**AIB granularity lives inside the page,** as an offers table sorted by price,
plus one insight line:

> RTX 5070: 2 499 zł (Gigabyte Windforce) → 3 199 zł (ASUS Strix).
> 28% more money for ~2% more card.

---

## 3. Price statistics

One number per job. They are not competing options.

```
p_buy  = min(offers where in_stock
                        and first_party     # not marketplace/3rd-party sellers
                        and new             # not outlet / powystawowy / refurbished
                        and shippable
                        and not_bundle)     # no GPU+PSU composite prices

p_ref  = median(per-store minima)           # each store votes once

quarantine if p_buy < 0.7 × p_ref           # hold, do not publish as a bargain
```

- **`p_buy` is the headline price** and the ranking input. It is what a buyer
  actually pays, and it is what the Ceneo link points at.
- **`p_ref` is "typical street price"** — used for the `−6% vs typowa` badge and
  as the outlier sanity check. It is deliberately **not** the median of all
  listings: with 15 variants at one store and 3 at another, the median of
  listings is just "which store carries the most AIB SKUs". Per-store minima
  give each store one vote.
- **The median is a filter, not a value.** At n≈5–15 observations per chip, the
  median of 5 values is literally the 3rd value — it offers no robustness. The
  actual defence against garbage is the filter list plus the quarantine rule.

**Rules that keep the ranking honest:**

1. **Never mix statistics across chips.** If some chips are ranked on `p_buy`
   and others on `p_ref` because data was sparse, the leaderboard compares
   different quantities and lies silently. **Drop the chip instead.**
2. **Keep the statistic independent of the money.** If direct store programmes
   with differing commissions are added later, ranking by "cheapest store I earn
   from" is the corruption path, and it is invisible to users.
3. **Variant-aware:** the price of a chip is the cheapest *in-stock* variant,
   which is what a buyer does.

The `−% vs typowa cena` badge is valuable because it **works on day one, with a
single snapshot and no history.**

---

## 4. The ranking

```
perf(g)   = 100 × geomean_i( fps_i(g) / fps_i(reference) )   # scoped to a resolution
value(g)  = perf(g) / p_buy(g) × 1000                        # points per 1000 zł
verdict   = percentile rank of value within the feasible set
```

**Feasibility gate before ranking.** Pure FPS-per-złoty always recommends a
weak card and every hardware community dismisses it. Filter first, then rank:

- VRAM floor for the target resolution
- required feature set (upscaler generation, AV1, etc.)
- PSU wattage / connectors, card length (offer-level attributes)

**One leaderboard is wrong.** Value inverts with resolution: 1080p favours cheap
cards, 4K collapses them. v1 ships three scores — 1440p raster, 1440p RT, VRAM —
and lets the user pick. A single number will be mocked, correctly.

**Cross-tier comparison is allowed and desirable** — but as a step-down
suggestion ("the 5060 Ti 16GB at 1 899 zł beats the 5070 at 2 499 zł on złoty per
FPS"), not as a flat table of everything. Comparison scope: **currently buyable
new, in stock, current + previous generation**; pair within ±1 generation and
±30% price. No N×N matrix — a two-slot comparator instead.

---

## 5. Performance data — the actual asset

Prices are rentable. **Performance is the IP.** And this is the one area with a
licensing risk the pricing plan does not have.

| Option | Cost | Verdict |
|---|---|---|
| Measure in-house (3–5 games × 3 resolutions) | hardware + time | the moat; v2+ |
| Spec-derived proxy (shader/TFLOPS, bandwidth, cache) | free | **v1**, clearly labelled as estimate with published methodology |
| Licence a benchmark dataset | money | later, if it works |
| Scrape TechPowerUp / YouTube results | **no** | copyrighted compilation + database right; the single worst legal exposure in the project |

Start with the spec proxy, publish the methodology, migrate to measurements.
A score you derived and can defend is the product; a score you copied is a
liability.

---

## 6. Data sources

**v1: x-kom and Morele.** Between them they cover most of the relevant Polish
GPU market, and both are workable.

Order by *market coverage*, not technical difficulty. MediaExpert and MediaMarkt
are deferred indefinitely: MediaMarkt GPU prices typically run 10–20% above
x-kom/Morele, so they are ~10% of the value for ~80% of the maintenance burden.
Allegro and OLX are out of v1 but are the obvious coverage gaps to revisit.

**Source hygiene:** exclude marketplace/third-party sellers, or flag them
separately. A no-reputation seller at 1 899 zł for a 5070 is not a price.

### Matching (the real engineering work)

`Gigabyte GeForce RTX 5070 WINDFORCE OC 12G GV-N5070WF3OC-12GD` → `rtx-5070-12gb`

AIB titles are chaotic (`OC`, `OC V2`, `Rev 2.0`, `SFF`, `White`, `Ice`, `Aero`,
`Eagle`, `Gaming OC`, `Ventus 3X`). Approach, in order:

1. structured data first — `gtin13` / `mpn` from JSON-LD where present
2. AIB part number embedded in the title (`GV-N5070WF3OC-12GD`)
3. small per-store rule table
4. hand-maintained `overrides.yaml` for the remaining ~10–15%

Do not write a clever regex at 60 SKUs. The override file takes an hour and
saves weeks.

**Sanity check before publishing:** if the cheapest offer is >40% below the
second cheapest, that is a matching bug, not a deal.

---

## 7. Architecture

Everything statically generated, rebuilt when prices update.

```
[self-hosted: small always-on machine]
  scrape.py  ← HTTP client, 2 stores, tens of SKUs, a few times a day
      │
      ├─ data/prices.json      current snapshot (consumed at build time)
      └─ data/history.jsonl    append-only, one line per SKU per run
      │
  build.py  ← Jinja2 → dist/   ~40–60 pages, renders in <1s
      │
  wrangler pages deploy dist
      │
  <project>.pages.dev  → custom .pl domain later
```

**Hosting: Cloudflare Pages free** — unlimited bandwidth, 500 builds/month, 1
concurrent build, 20k files per deployment, 20-minute build cap, custom domain
with TLS, no commercial-use restriction.

**Not Vercel:** Hobby is explicitly "non-commercial, personal use only" — an
affiliate-monetised site is commercial.

**No database.** `history.jsonl` is the price_snapshots table and the git log is
the audit trail. 40–60 SKUs × 4 runs/day ≈ 87k lines/year ≈ 10 MB. No Postgres,
no SQLite, no Tailscale, no remote DB sync.

**Bake prices into the HTML** rather than fetching JSON client-side: the 40–60
model pages need the price in the markup to rank for *"rtx 5070 cena"*, and
search traffic is what feeds the Ceneo clicks.

**Staleness guard in the build:** refuse to deploy if
`max(scraped_at) > 8h`. A static artifact can then carry its own honesty —
bake `Ceny z 14:05, 31 października` into the footer.

**Cadence budget:** a handful of rebuilds per day lands well under the 500/month
ceiling (~100–150). Hourly rebuilds (720/month) would exceed it — so **alerts cannot live in the static
rebuild path.** When alerts arrive they belong on a Worker + KV (100k req/day
free) or a separate job.

**Scheduling:** systemd timer, not cron — `Persistent=true` catches runs missed
while the host was off, `RandomizedDelaySec` provides the jitter politeness wants.

```ini
[Timer]
OnCalendar=<every few hours, not on the hour>
RandomizedDelaySec=120
Persistent=true
```

**Single point of failure:** the host. If it dies, prices go stale — which the
footer timestamp makes visible. Add a dead-man's switch (healthchecks.io ping
per cycle) when the schedule becomes load-bearing.

---

## 8. Site structure

- `/` — sortable leaderboard, filters: budget, resolution, VRAM floor
- `/gpu/rtx-5070-12gb/` — one page per chip+VRAM (~40–60 pages). Targets
  *"rtx 5070 cena"*, *"rtx 5070 opłacalność"*, *"rtx 5070 vs 4070 super"*
- `/porownaj/a-vs-b/` — two-slot comparator (or a client-side variant of it)
- `/metodologia/` — the filter list, the perf formula, the data vintage. This
  page is the trust moat and should be written before the product is defended.

**Do not** generate a page per AIB SKU (`/gpu/gigabyte-rtx-5070-windforce-oc/`):
hundreds of thin near-duplicate pages, self-cannibalising rankings, permanent
maintenance, for queries nobody types. Split out an AIB page later only if data
shows demand.

Per row: `p_buy`, `−% vs typowa` badge, cheapest store name, timestamp, link.

---

## 9. Monetisation

- Ceneo affiliate link with PID, generated at build time:
  `https://www.ceneo.pl/<product_id>;pid=<PID>`
- **Distinct sub-ID per page/placement** — the only attribution channel a static
  site needs, no backend required
- `rel="sponsored nofollow noopener"`
- Visible disclosure ("linki afiliacyjne") — UOKiK is active on this
- Keep the option of direct store programmes open; keep price logic independent
  of commission logic (§3 rule 2)

**Ceneo is the exit, not the data source.** The partner programme provides
affiliate links carrying a PID, Ceneo-hosted wishlists, and links to Ceneo's price
history. It does not provide a product feed, an API, or historical price series.
Komper therefore obtains prices from stores directly and uses Ceneo only as the
outbound link — which keeps the data path and the revenue path independent of
each other.

---

## 10. Data practice

Komper is a courteous crawler, and states its policy rather than relying on a
technicality.

**Robots and opt-outs.** Each store's `robots.txt` is read before any request.
Disallowed paths are not fetched. Published crawl delays and opt-outs are
honoured, and if a store asks us to stop, we stop.

**Identification.** Requests come from a single, stable address, with a contact
address published for the site's operator. No proxies, no IP rotation, no
challenge-solving. If a store blocks us, that is a legitimate answer and we
accept it.

**Politeness.** One request at a time per store, randomised delay between
requests, sequential store crawling, exponential backoff on 429/403, and a hard
stop after repeated failures.

**Data hygiene.** No personal data, no seller names, no review authors, no
republished raw HTML, no catalogue mirror. Only derived prices, rankings and
recommendations — with the data vintage shown on every page.

**Scope.** Tens of SKUs across two stores. This is a reading of public retail
prices for a handful of products, not a copy of anyone's catalogue.

---

## 11. Open questions (these decide the build)

1. **Do x-kom / Morele publish JSON-LD with `price` and `gtin13`/`mpn`?**
   If yes at both, matching becomes close to a join and the project gets
   materially cheaper. *Probe: one product page per store.* — next action.
2. **May Ceneo partner data be stored/cached/displayed outside links and
   wishlists?** Read the regulamin; get it in writing from `partnerzy@ceneo.pl`.
3. **Where does performance data come from long-term** — measure, or keep the
   labelled spec proxy? This is the difference between an asset and a wrapper.
4. **Does anyone want this?** A hand-curated v1 answers it for the price of a
   weekend; no scraper needed to find out.

---

## 12. Build order

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **P0** | This document | agreed scope |
| **P1** | Hand-curated 40–60 chips (CSV + perf scores), ranking page, manual prices, live on `pages.dev` | indexable and someone can use it |
| **P2** | Scraper for 2 stores on a schedule, automated rebuild, staleness guard | prices refresh unattended for 2 weeks |
| **P3** | Ceneo PID + per-page sub-ID + disclosure + clicks visible in panel | attribution proven end-to-end |
| **P4** | `history.jsonl` → 30/90-day percentiles → deal score → alerts | temporal verdict beats cross-sectional badge |
| **P5** | Own benchmark suite; more stores; used market (separately labelled) | performance index is owned |

**P1 deliberately comes before the scraper.** The product is the model; prove
the model by hand before automating the pipe. If the ranking is good, people
screenshot and argue about it — that is the distribution. If it is mediocre, no
cadence saves it.

**The ordered task queue with definitions of done lives in [NEXT.md](NEXT.md).**
This table is the shape of the work; that file is what to do next and how to tell
it is finished. There is a gate between P1 and P2: ship by hand, wait two weeks,
and if nobody uses it, stop rather than build the scraper.

---

## 13. Decision log

| Decision | Choice | Reason |
|---|---|---|
| Unit of comparison | chip + VRAM | perf is a chip property; VRAM changes the product |
| AIB handling | offer attribute, never a page | price spread ≫ perf spread |
| Price statistic | `p_buy` = filtered min | it is what the buyer pays; median adds no robustness at n≈5 |
| Reference price | median of per-store minima | avoids weighting by catalogue size |
| Deal signal at launch | `−% vs typowa` | works on a single snapshot, no history needed |
| History in v1 | excluded | it is the commodity Ceneo already gives away |
| Rendering | static, prices baked in | SEO needs price in HTML; Ceneo clicks come from search |
| Data freshness | rebuild on update, a few times a day | well under the 500 builds/month ceiling; hourly would exceed it |
| Database | none — JSON + JSONL + git | 10 MB/year; Postgres is ceremony at this size |
| Host | Cloudflare Pages | free bandwidth, commercial use allowed; Vercel Hobby is not |
| Scraping transport | plain HTTP client | simplest thing that works; revisit only if a store requires more |
| Stores | x-kom + Morele first | market coverage, not difficulty |
| Monetisation | Ceneo PID redirect | pre-qualified high-intent clicks |

---

## 14. Verified facts (re-check before relying on them)

Checked 2026-10-31:

- Cloudflare Pages free: 500 builds/month, 1 concurrent build, 20k files,
  20-minute build cap, unlimited bandwidth.
- Vercel Hobby: "restricts users to non-commercial, personal use only".
- Ceneo Partner Program scope: PID links, Ceneo-hosted wishlists, price-history
  links, app/scanner — **no product feed or API for publishers found.**

These are point-in-time facts. Robots files, free tiers and storefront markup all
change; re-verify before depending on any of them.
