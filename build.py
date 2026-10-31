#!/usr/bin/env python3
"""Static build: data -> dist/.

Reads data/gpus.csv (chip specs) and data/prices.json (listings), computes the
performance proxy, the buy price and the value ranking, and renders static HTML.

Deliberately boring: Jinja2, no framework, no client-side data fetching. Prices
are baked into the markup so per-chip pages can rank in search.

    python3 build.py
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SITE = os.environ.get("SITE_URL", "https://komper.pages.dev").rstrip("/")
MAX_AGE = timedelta(hours=8)
# one listing is a listing, not a market price. Two is the minimum for ranking.
MIN_OFFERS = 2

# Documented in /metodologia/. The proxy is not a measurement and says so.
COMPUTE_EXP = 0.5
BANDWIDTH_EXP = 0.25
REF = 100.0


def load_chips() -> list[dict]:
    rows = []
    for row in csv.DictReader((ROOT / "data" / "gpus.csv").open()):
        for col in ("vram_gb", "shaders", "boost_mhz", "bus_bits", "mem_mhz",
                    "psu_w", "length_mm", "arch_eff", "perf_adj"):
            raw = row.get(col) or ""
            row[col] = float(raw) if raw.strip() else None
        row["complete"] = all(
            row[c] for c in ("shaders", "boost_mhz", "bus_bits", "mem_mhz")
        )
        rows.append(row)
    return rows


def load_listings() -> tuple[list[dict], datetime]:
    blob = json.loads((ROOT / "data" / "prices.json").read_text())
    scraped = datetime.fromisoformat(blob["scraped_at"])
    age = datetime.now(timezone.utc) - scraped
    if age > MAX_AGE:
        print(
            f"WARNING: prices are {age} old (target {MAX_AGE}). "
            "Building anyway and flagging it on the page - a stale build with a "
            "visible warning beats a broken deploy.",
            file=sys.stderr,
        )
    return blob["records"], scraped, age > MAX_AGE


def proxy(chip: dict) -> float:
    """Performance proxy. Transparent, reproducible, and not a benchmark."""
    tflops = chip["shaders"] * 2 * (chip["boost_mhz"] / 1000) / 1000
    bandwidth = (chip["bus_bits"] / 8) * (chip["mem_mhz"] / 1000)
    return (
        (tflops**COMPUTE_EXP)
        * (bandwidth**BANDWIDTH_EXP)
        * chip["arch_eff"]
        * chip["perf_adj"]
    )


def price_stats(chips: list[dict], listings: list[dict]) -> dict:
    by_chip: dict[tuple[str, int], list[dict]] = {}
    seen: set[str] = set()
    for rec in listings:
        if not rec.get("price_pln") or not rec.get("vram_gb"):
            continue
        if rec.get("url") and rec["url"] in seen:
            continue  # the store's pagination repeats the same page server-side
        if rec.get("is_outlet") or rec.get("in_stock") is False:
            continue  # outlet units and unavailable listings are not market prices
        seen.add(rec.get("url") or "")
        by_chip.setdefault((rec["chip"], int(rec["vram_gb"])), []).append(rec)

    stats = {}
    for chip in chips:
        offers = sorted(
            by_chip.get((chip["chip"], int(chip["vram_gb"] or 0)), []),
            key=lambda r: r["price_pln"],
        )
        if not offers:
            continue
        per_store: dict[str, float] = {}
        for rec in offers:
            store = rec["store"]
            per_store[store] = min(per_store.get(store, 1e9), rec["price_pln"])
        p_buy = min(per_store.values())
        # median of per-store minima: each store votes once (PLAN.md section 3)
        p_ref = median(per_store.values())
        stats[chip["key"]] = {
            "offers": len(offers),
            "stores": len(per_store),
            "p_buy": p_buy,
            "p_ref": p_ref,
            # only meaningful with two or more stores; with one, p_ref == p_buy
            "deal": (p_buy / p_ref - 1) if len(per_store) >= 2 else None,
            "spread": offers[-1]["price_pln"] / offers[0]["price_pln"] - 1,
            "cheapest": offers[0],
            "all": offers,
        }
    return stats


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " zł"


def main() -> int:
    chips = load_chips()
    listings, scraped, stale = load_listings()

    ranked_raw = [c for c in chips if c["complete"]]
    top = max(proxy(c) for c in ranked_raw) if ranked_raw else 1.0

    stats = price_stats(chips, listings)
    rows = []
    for chip in ranked_raw:
        perf = proxy(chip) / top * REF
        chip["perf"] = round(perf, 1)
        stat = stats.get(chip["key"])
        chip["stats"] = stat
        if stat and stat["offers"] >= MIN_OFFERS:
            chip["value"] = round(perf / stat["p_buy"] * 1000, 1)
            rows.append(chip)

    rows.sort(key=lambda c: c["value"], reverse=True)
    # a chip without prices is reported, never ranked (PLAN.md section 3, rule 1)
    unpriced = [
        c["chip"] + f" {int(c['vram_gb'])}GB"
        for c in ranked_raw
        if c["key"] not in stats
    ]
    incomplete = [
        c["chip"] + f" {int(c['vram_gb'])}GB" for c in chips if not c["complete"]
    ]
    single = [
        c["chip"] + f" {int(c['vram_gb'])}GB"
        for c in ranked_raw
        if c["key"] in stats and stats[c["key"]]["offers"] < MIN_OFFERS
    ]

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    shutil.copy(ROOT / "assets" / "style.css", DIST / "assets" / "style.css")

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = money

    ctx = {
        "rows": rows,
        "scraped": scraped.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "listings": len(listings),
        "unpriced": unpriced,
        "incomplete": incomplete,
        "single": single,
        "site": SITE,
        "stale": stale,
        "compute_exp": COMPUTE_EXP,
        "bandwidth_exp": BANDWIDTH_EXP,
    }

    paths: list[str] = []

    (DIST / "index.html").write_text(
        env.get_template("index.html.j2").render(path="/", **ctx)
    )
    paths.append("/")

    (DIST / "metodologia").mkdir()
    (DIST / "metodologia" / "index.html").write_text(
        env.get_template("metodologia.html.j2").render(path="/metodologia/", **ctx)
    )
    paths.append("/metodologia/")

    (DIST / "gpu").mkdir()
    for chip in rows:
        rel = f"/gpu/{chip['key']}"
        (DIST / f"gpu/{chip['key']}.html").write_text(
            env.get_template("chip.html.j2").render(chip=chip, path=rel, **ctx)
        )
        paths.append(rel)

    # sitemap and robots: an unindexed price comparison is worth nothing
    lastmod = scraped.strftime("%Y-%m-%d")
    urls = "".join(
        f"<url><loc>{SITE}{p}</loc><lastmod>{lastmod}</lastmod></url>" for p in paths
    )
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>\n"
    )
    (DIST / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n" f"\nSitemap: {SITE}/sitemap.xml\n"
    )

    print(f"built {1 + 1 + len(rows)} pages from {len(listings)} listings")
    print(f"  ranked: {len(rows)}   unpriced: {len(unpriced)}   incomplete: {len(incomplete)}")
    for chip in rows[:5]:
        print(
            f"  {chip['chip']:<18}{int(chip['vram_gb']):>3}GB"
            f"  perf {chip['perf']:>5}  {money(chip['stats']['p_buy']):>10}"
            f"  value {chip['value']:>6}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
