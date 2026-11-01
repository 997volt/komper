# Komper

**GPU price/performance for Poland — answers "what is a good buy".**

Live: **https://komper-git.pages.dev** — deployed from `main` by Cloudflare Pages on every push.

Status: planning, with a first working build. No code in this repository yet, by design. The
reasoning, the data model, the constraints and the build order are in
[PLAN.md](PLAN.md).

The one-line shape of the thing:

> A statically generated site that ranks GPUs by performance per złoty,
> shows what each card actually costs today across Polish stores, and sends
> the user to the cheapest credible offer via a Ceneo affiliate link.

Not a shop. Not a content farm. Not a price aggregator competing with Ceneo on
data collection — it competes on **judgment**.

## Updating prices

The site is rebuilt by Cloudflare Pages on every push to `main`. Prices are
harvested on a machine with a normal internet connection — never inside the
Pages build, which only renders the committed data.

```bash
python3 tools/harvest.py --pages 3 --details 12   # refresh data/gpus.csv + data/prices.json
python3 build.py                                  # optional: preview locally in dist/
git add data && git commit -m "prices: $(date -u +%F)" && git push
```

`./deploy.sh` still works as a manual fallback (it builds and uploads `dist/`
without git), but normal deploys need no credential at all.

## Adding a chip that has prices but no specs

Prices come from category listings, which cap at 30 products per store page.
Specs are per chip, so they are fetched separately from Morele's declared product
sitemap — one request per chip, and only for chips that are missing:

```bash
python3 tools/specs.py        # appends to data/gpus.csv, never overwrites
```

A chip with no spec sheet stays unranked rather than being estimated.

## Price history

`data/history/YYYY-MM.jsonl` — one row per store + chip + VRAM per harvest run,
holding the cheapest price and the number of offers seen.

```json
{"t":"2026-11-01T21:52:02+00:00","s":"morele","c":"Arc B570","v":10,"p":1599.0,"n":1}
```

Append-only and sharded by month so git stores each month's file once. Nothing
reads it yet: the site is built from `data/prices.json` alone, so recording
history changes no page. It exists so that "cheapest in 30 days" is possible
later without a backfill — history cannot be reconstructed after the fact.
