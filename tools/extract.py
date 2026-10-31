#!/usr/bin/env python3
"""One-shot probe: fetch a product page and normalise its schema.org offer.

This is NOT the pipeline. No scheduler, no retries, no database. It exists to
prove the data path for both stores before anything is built on top of it.

    python3 tools/extract.py URL [URL ...] --out data/prices.json

Extraction order follows PLAN.md section 6: structured data first, then the
name/slug, then rules. AIB titles are never trusted on their own.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STORES = {"x-kom.pl": "x-kom", "www.x-kom.pl": "x-kom", "morele.net": "morele", "www.morele.net": "morele"}

# Chip names appear in a predictable shape on both storefronts.
CHIP = re.compile(
    r"\b(Radeon RX \d{4}(?: XT| GRE)?"
    r"|GeForce RTX \d{4}(?: Ti| SUPER| Super)?"
    r"|Arc [AB]\d{3})\b",
    re.I,
)
VRAM = re.compile(r"\b(\d{1,2})\s?GB\b", re.I)
LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def product_ld(html: str) -> dict | None:
    for block in LD.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def chip_from_properties(ld: dict) -> str | None:
    """Morele publishes the chipset as a structured property. Prefer it."""
    for prop in ld.get("additionalProperty") or []:
        if not isinstance(prop, dict):
            continue
        if "chipset" in (prop.get("name") or "").lower():
            match = CHIP.search(str(prop.get("value") or ""))
            if match:
                return normalise_chip(match.group(1))
    return None


def normalise_chip(raw: str) -> str:
    s = raw.strip()
    # canonical casing: "RX 9070 XT", "RTX 5060 Ti", "Arc B580"
    s = re.sub(r"(?i)\brtX\b", "RTX", s)
    s = re.sub(r"(?i)\bsuper\b", "SUPER", s)
    s = re.sub(r"(?i)\bti\b", "Ti", s)
    return re.sub(r"\s+", " ", s)


def vram_from(slug_or_name: str) -> int | None:
    match = VRAM.search(slug_or_name.replace("-", " "))
    return int(match.group(1)) if match else None


def extract(url: str) -> dict:
    host = urllib.parse.urlsplit(url).hostname or ""
    store = STORES.get(host, host)
    html = fetch(url)
    ld = product_ld(html)
    if ld is None:
        raise SystemExit(f"no Product JSON-LD found at {url}")

    name = str(ld.get("name") or "")
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    seller = (offer.get("seller") or {}).get("name")

    ship = offer.get("shippingDetails") or {}
    rate = (ship.get("shippingRate") or {}) if isinstance(ship, dict) else {}

    return {
        "store": store,
        "url": url,
        "store_sku": str(ld.get("sku") or ""),
        "mpn": (ld.get("mpn") or None),
        "gtin13": (ld.get("gtin13") or None),
        "brand": (ld.get("brand") or {}).get("name") if isinstance(ld.get("brand"), dict) else None,
        "name": name,
        "chip": chip_from_properties(ld) or (normalise_chip(m.group(1)) if (m := CHIP.search(name)) else None),
        "vram_gb": vram_from(name) or vram_from(url),
        "price_pln": offer.get("price"),
        "currency": offer.get("priceCurrency"),
        "in_stock": "instock" in str(offer.get("availability", "")).lower(),
        "condition": str(offer.get("itemCondition", "")).rsplit("/", 1)[-1] or None,
        "seller": seller,
        # morele publishes a seller; a marketplace listing would name someone else.
        # x-kom publishes none, so first-party status is unknown rather than assumed.
        "first_party": ("morele" in seller.lower() or "x-kom" in seller.lower())
        if seller
        else None,
        "shipping_pln": [rate.get("minValue"), rate.get("maxValue")] if rate else None,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--out", default="data/prices.json")
    args = ap.parse_args()

    records = []
    for url in args.urls:
        rec = extract(url)
        records.append(rec)
        print(
            f"{rec['store']:>7}  {str(rec['price_pln']):>6} {rec['currency'] or '':<4}"
            f"  {rec['chip'] or '?':<16} {rec['vram_gb'] or '?':>2}GB"
            f"  stock={rec['in_stock']!s:<5} gtin={'yes' if rec['gtin13'] else 'no'}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "records": records},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"\n{len(records)} records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
