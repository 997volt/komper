#!/usr/bin/env python3
"""Harvest GPU listings and per-chip specs from morele.

Two-level fetch, as PLAN.md section 7 describes:
  1. category sweep  - one request per page, 30 listings with prices each
  2. detail fetch    - one request per chip, for the machine-readable spec sheet

Outputs:
  data/prices.json  every listing seen, with price and stock
  data/gpus.csv     one row per chip + VRAM, with the specs the proxy needs

Nothing here is scheduled or retried. It is a harvesting tool, run by hand.

    python3 tools/harvest.py --pages 3 --details 14
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CATEGORY = "https://www.morele.net/kategoria/karty-graficzne-12/"
XKOM_CATEGORY = "https://www.x-kom.pl/g-5/c/345-karty-graficzne.html"
LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)

CHIP = re.compile(
    r"\b(Radeon RX \d{4}(?: XT| GRE)?"
    r"|GeForce RTX \d{4}(?: Ti| SUPER)?"
    r"|Arc [AB]\d{3})\b",
    re.I,
)
VRAM = re.compile(r"\b(\d{1,2})\s?GB\b", re.I)

# Polish attribute names -> our columns
SPEC_MAP = {
    "procesory strumieniowe": "shaders",
    "taktowanie rdzenia w trybie boost": "boost_mhz",
    "szyna danych": "bus_bits",
    "taktowanie pamięci": "mem_mhz",
    "rekomendowana moc zasilacza": "psu_w",
    "długość karty": "length_mm",
    "ilość pamięci ram": "vram_gb",
}


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def ld_blocks(html: str):
    for block in LD.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        yield from (data if isinstance(data, list) else [data])


def number(value) -> float | None:
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value or "").replace(" ", ""))
    return float(match.group(0).replace(",", ".")) if match else None


def normalise_chip(raw: str) -> str:
    s = re.sub(r"(?i)\brtx\b", "RTX", raw.strip())
    s = re.sub(r"(?i)\bsuper\b", "SUPER", s)
    s = re.sub(r"(?i)\bti\b", "Ti", s)
    return re.sub(r"\s+", " ", s)


def arch_of(chip: str) -> str:
    if "Radeon" in chip:
        return "RDNA4" if int(chip.split()[2]) >= 9000 else "RDNA3"
    if "RTX" in chip:
        gen = int(re.search(r"\d{4}", chip).group(0))
        return "Blackwell" if gen >= 5000 else "Ada"
    if "Arc" in chip:
        return "Battlemage"
    return "?"


def sweep(page: int) -> list[dict]:
    url = CATEGORY if page == 1 else f"{CATEGORY}?page={page}"
    html = fetch(url)
    out = []
    for block in ld_blocks(html):
        if block.get("@type") != "ItemList":
            continue
        for el in block.get("itemListElement") or []:
            item = el.get("item") or {}
            name = item.get("name") or ""
            offer = item.get("offers") or {}
            chip_match = CHIP.search(name)
            if not chip_match:
                continue
            vram_match = VRAM.search(name)
            out.append(
                {
                    "store": "morele",
                    "url": item.get("url"),
                    "name": name,
                    "chip": normalise_chip(chip_match.group(1)),
                    "vram_gb": int(vram_match.group(1)) if vram_match else None,
                    "price_pln": number(offer.get("price")),
                    "currency": offer.get("priceCurrency"),
                }
            )
    return out


def sweep_xkom() -> list[dict]:
    """x-kom renders its product tiles into window.__INITIAL_STATE__.

    One request yields the whole first page: name, price, availability, outlet
    flag and the product link. No specs though - those still come from morele.
    """
    html = fetch(XKOM_CATEGORY)
    match = re.search(r"window\.__INITIAL_STATE__\['app'\]\s*=\s*", html)
    if not match:
        return []
    state, _ = json.JSONDecoder().raw_decode(html, match.end())

    out: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            name = node.get("fullName") or node.get("name")
            price = node.get("price")
            link = node.get("productLink")
            if (
                isinstance(name, str)
                and isinstance(price, (int, float))
                and "priceInfo" in node
                and link
            ):
                chip_match = CHIP.search(name)
                if chip_match:
                    vram_match = VRAM.search(name)
                    status = str(node.get("availabilityStatus") or "")
                    out.append(
                        {
                            "store": "x-kom",
                            "url": "https://www.x-kom.pl" + link,
                            "name": name,
                            "chip": normalise_chip(chip_match.group(1)),
                            "vram_gb": int(vram_match.group(1)) if vram_match else None,
                            "price_pln": float(price),
                            "currency": "PLN",
                            "in_stock": status.lower().startswith("avail") or None,
                            "is_outlet": bool(node.get("isOutlet")),
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(state)
    return out


def details(url: str) -> dict:
    html = fetch(url)
    for block in ld_blocks(html):
        if block.get("@type") != "Product":
            continue
        props = {
            (p.get("name") or "").strip().lower(): p.get("value")
            for p in block.get("additionalProperty") or []
            if isinstance(p, dict)
        }
        rec = {col: number(props[key]) for key, col in SPEC_MAP.items() if key in props}
        rec["gtin13"] = block.get("gtin13")
        rec["mpn"] = block.get("mpn")
        offer = block.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        rec["seller"] = (offer.get("seller") or {}).get("name")
        rec["in_stock"] = "instock" in str(offer.get("availability", "")).lower()
        rec["price_pln"] = number(offer.get("price"))
        return rec
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    # morele paginates client-side, so only page 1 exists server-side.
    # Raising this only repeats the same 30 products (they are deduped below).
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--details", type=int, default=14)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--data", default="data")
    args = ap.parse_args()
    data = Path(args.data)

    listings: list[dict] = []
    for page in range(1, args.pages + 1):
        got = sweep(page)
        print(f"morele page {page}: {len(got)} gpu listings")
        listings += got
        time.sleep(args.delay)

    xkom = sweep_xkom()
    print(f"x-kom: {len(xkom)} gpu listings")
    listings += xkom
    time.sleep(args.delay)

    # the category page renders one server-side ItemList and paginates client-side,
    # so sweep pages repeat the same 30 products. Dedupe on url before anything else.
    seen: set[str] = set()
    unique = []
    for rec in listings:
        if rec["url"] and rec["url"] not in seen:
            seen.add(rec["url"])
            unique.append(rec)
    if len(unique) != len(listings):
        print(f"deduped {len(listings) - len(unique)} repeated listings")
    listings = unique

    # cheapest listing per (chip, vram) becomes the representative for specs
    groups: dict[tuple[str, int], list[dict]] = {}
    for rec in listings:
        if rec["chip"] and rec["vram_gb"]:
            groups.setdefault((rec["chip"], rec["vram_gb"]), []).append(rec)
    print(f"{len(groups)} distinct chip+vram groups from {len(listings)} listings")

    rows = []
    for (chip, vram), members in sorted(groups.items(), key=lambda kv: kv[0][0]):
        if len(rows) >= args.details:
            break
        with_specs = [r for r in members if r["store"] == "morele"]
        if not with_specs:
            print(f"  {chip:<18} {vram:>2}GB  no morele listing, specs unavailable")
            continue
        cheapest = min(with_specs, key=lambda r: r["price_pln"] or 1e9)
        spec = details(cheapest["url"])
        time.sleep(args.delay)
        print(f"  {chip:<18} {vram:>2}GB  {spec.get('shaders') or '?':>5} sp  {spec.get('price_pln')}")
        rows.append(
            {
                "key": re.sub(r"[^a-z0-9]+", "-", f"{chip} {vram}gb".lower()).strip("-"),
                "chip": chip,
                "vram_gb": vram,
                "arch": arch_of(chip),
                "shaders": spec.get("shaders"),
                "boost_mhz": spec.get("boost_mhz"),
                "bus_bits": spec.get("bus_bits"),
                "mem_mhz": spec.get("mem_mhz"),
                "psu_w": spec.get("psu_w"),
                "length_mm": spec.get("length_mm"),
                "arch_eff": 1.0,
                "perf_adj": 1.0,
                "note": f"specs from morele listing {cheapest['url'].rsplit('-', 1)[-1].strip('/')}; "
                f"{len(members)} offers across {len({r['store'] for r in members})} store(s)",
            }
        )

    data.mkdir(exist_ok=True)
    with (data / "gpus.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (data / "prices.json").write_text(
        json.dumps(
            {
                "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "records": listings,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"\n{len(rows)} chips -> {data/'gpus.csv'}")
    print(f"{len(listings)} listings -> {data/'prices.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
