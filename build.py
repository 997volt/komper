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

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SITE = os.environ.get("SITE_URL", "https://komper-git.pages.dev").rstrip("/")
MAX_AGE = timedelta(hours=8)
# one listing is a listing, not a market price. Two is the minimum for ranking.
MIN_OFFERS = 2
# Below this, a card cannot hold a modern 1080p texture set, so a high
# points-per-zloty score is arithmetically true and practically useless.
MIN_VRAM_GB = 8

# Documented in /metodologia/. The proxy is not a measurement and says so.
COMPUTE_EXP = 0.5
BANDWIDTH_EXP = 0.25
REF = 100.0
# Budget bands for the "what to buy" summary. A ranking is not a recommendation:
# people arrive with a budget, not a column to sort.
BANDS = [
    (0, 2000, "do 2 000 zł"),
    (2000, 3000, "2 000 – 3 000 zł"),
    (3000, 4500, "3 000 – 4 500 zł"),
    (4500, 10**9, "powyżej 4 500 zł"),
]


def target_of(perf: float, vram: float) -> str:
    """Rough resolution band. Editorial, and stated as such in /metodologia/."""
    if perf >= 45 and vram >= 16:
        return "4K"
    if perf >= 28 and vram >= 8:
        return "1440p"
    return "1080p"


def chip_label(chip: dict) -> str:
    vram = chip.get("vram_gb")
    return f"{chip['chip']} {int(vram)}GB" if vram else chip["chip"]


def pl_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n == 1:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def load_chips() -> list[dict]:
    rows = []
    for row in csv.DictReader((ROOT / "data" / "gpus.csv").open()):
        for col in ("vram_gb", "shaders", "boost_mhz", "bus_bits", "mem_mhz",
                    "psu_w", "length_mm", "arch_eff", "perf_adj"):
            raw = row.get(col) or ""
            value = float(raw) if raw.strip() else None
            # calibration columns default to neutral rather than None: proxy()
            # multiplies by them, and a blank cell in a hand-edited CSV should
            # mean "no adjustment", not a traceback
            if value is None and col in ("arch_eff", "perf_adj"):
                value = 1.0
            row[col] = value
        row["complete"] = all(
            row[c] for c in ("shaders", "boost_mhz", "bus_bits", "mem_mhz")
        )
        rows.append(row)
    return rows


def load_listings() -> tuple[list[dict], datetime, bool]:
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
        stats[chip["key"]] = {
            "offers": len(offers),
            "stores": len(per_store),
            "p_buy": p_buy,
            "spread": offers[-1]["price_pln"] / offers[0]["price_pln"] - 1,
            "cheapest": offers[0],
            "all": offers,
        }
    return stats


def money(value: float | None) -> str:
    """Polish formatting. Keeps grosze when there are any: a price comparison
    that rounds 2 658,89 to 2 659 is wrong by a złoty."""
    if value is None:
        return "—"
    if abs(value - round(value)) < 0.005:
        return f"{value:,.0f}".replace(",", " ") + " zł"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def main() -> int:
    chips = load_chips()
    listings, scraped, stale = load_listings()

    ranked_raw = [c for c in chips if c["complete"]]
    top = max(proxy(c) for c in ranked_raw) if ranked_raw else 1.0

    stats = price_stats(chips, listings)
    page_chips = []
    for chip in ranked_raw:
        perf = proxy(chip) / top * REF
        chip["perf"] = round(perf, 1)
        chip["target"] = target_of(perf, chip["vram_gb"] or 0)
        stat = stats.get(chip["key"])
        chip["stats"] = stat
        if not stat:
            continue
        chip["value"] = round(perf / stat["p_buy"] * 1000, 1)
        # a page for every chip with a price, but only some are ranked
        if (chip["vram_gb"] or 0) < MIN_VRAM_GB:
            chip["excluded_reason"] = f"mniej niż {MIN_VRAM_GB} GB pamięci"
        elif stat["offers"] < MIN_OFFERS:
            chip["excluded_reason"] = "tylko jedna oferta w sklepach"
        else:
            chip["excluded_reason"] = None
        page_chips.append(chip)

    rows = [c for c in page_chips if c["excluded_reason"] is None]

    rows.sort(key=lambda c: c["value"], reverse=True)
    # the table is sorted by value, so that is the column that needs a visual scale
    top_value = max((c["value"] for c in rows), default=1) or 1
    for chip in rows:
        chip["value_pct"] = round(chip["value"] / top_value * 100, 1)

    picks = []
    for low, high, label in BANDS:
        candidates = [c for c in rows if low <= c["stats"]["p_buy"] < high]
        if candidates:
            picks.append({"label": label, "chip": max(candidates, key=lambda c: c["value"])})
    # a chip without prices is reported, never ranked (PLAN.md section 3, rule 1)
    unpriced = [chip_label(c) for c in ranked_raw if c["key"] not in stats]
    incomplete = [chip_label(c) for c in chips if not c["complete"]]
    single = [
        chip_label(c) for c in page_chips
        if c["excluded_reason"] == "tylko jedna oferta w sklepach"
    ]
    low_vram = [
        chip_label(c) for c in page_chips
        if c["excluded_reason"] and c["excluded_reason"].startswith("mniej niż")
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
        # a template that references a missing variable is a bug, not a blank
        undefined=StrictUndefined,
    )
    env.filters["money"] = money
    env.filters["pl_plural"] = pl_plural

    ctx = {
        "rows": rows,
        "picks": picks,
        "scraped": scraped.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "listings": len(listings),
        "unpriced": unpriced,
        "incomplete": incomplete,
        "single": single,
        "low_vram": low_vram,
        "min_vram": MIN_VRAM_GB,
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
    for chip in page_chips:
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

    print(f"built {2 + len(page_chips)} pages from {len(listings)} listings")
    print(f"  ranked: {len(rows)}  pages: {len(page_chips)}  low-vram: {len(low_vram)}"
          f"  single-offer: {len(single)}  unpriced: {len(unpriced)}  incomplete: {len(incomplete)}")
    for chip in rows[:5]:
        print(
            f"  {chip['chip']:<18}{int(chip['vram_gb']):>3}GB"
            f"  perf {chip['perf']:>5}  {money(chip['stats']['p_buy']):>10}"
            f"  value {chip['value']:>6}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
