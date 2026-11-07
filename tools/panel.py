#!/usr/bin/env python3
"""Build a pinned panel of product URLs from morele's declared sitemap.

The category listing shows 30 products and shifts between runs, so "the price
changed" and "a different product appeared" are indistinguishable in the data.
A pinned panel fixes the set: the same URLs are measured every time, so a change
in price is a change in price.

Selection is deterministic - chips already in data/gpus.csv, up to N URLs per
chip+VRAM, sorted by URL - so re-running this does not reshuffle the panel.

    python3 tools/panel.py --per-chip 4
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harvest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_SITEMAP = (
    "https://www.morele.net/product_active_sitemap_13_podzespoly_komputerowe.xml"
)
GPU_IN_URL = "karta-graficzna"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-chip", type=int, default=4, help="URLs to pin per chip+VRAM")
    ap.add_argument("--out", default="data/panel.csv")
    args = ap.parse_args()

    chips = {
        (row["chip"], int(row["vram_gb"]))
        for row in csv.DictReader((ROOT / "data" / "gpus.csv").open())
    }
    print(f"{len(chips)} chips in gpus.csv")

    html = harvest.fetch(COMPONENTS_SITEMAP, timeout=60)
    import re
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", html) if GPU_IN_URL in u]
    print(f"{len(urls)} gpu product urls in the sitemap")

    by_chip: dict[tuple[str, int], list[str]] = {}
    for url in urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        chip_match, vram_match = harvest.CHIP.search(slug), harvest.VRAM.search(slug)
        if not chip_match or not vram_match:
            continue
        key = (harvest.normalise_chip(chip_match.group(1)), int(vram_match.group(1)))
        if key in chips:
            by_chip.setdefault(key, []).append(url)

    rows, missing = [], []
    for chip, vram in sorted(chips):
        candidates = sorted(by_chip.get((chip, vram), []))
        if not candidates:
            missing.append((chip, vram))
            continue
        for url in candidates[: args.per_chip]:
            rows.append(
                {
                    "key": harvest.key_of(chip, vram),
                    "chip": chip,
                    "vram_gb": vram,
                    "url": url,
                }
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["key", "chip", "vram_gb", "url"])
        writer.writeheader()
        writer.writerows(rows)

    per_chip = {}
    for row in rows:
        per_chip[row["key"]] = per_chip.get(row["key"], 0) + 1
    print(f"\n{len(rows)} urls pinned across {len(per_chip)} chips -> {out}")
    counts = sorted(set(per_chip.values()))
    print(f"urls per chip: {counts}")
    thin = {k: v for k, v in per_chip.items() if v < args.per_chip}
    if thin:
        print(f"thinner than requested ({len(thin)}):")
        for k, v in sorted(thin.items()):
            print(f"   {k}: {v}")
    if missing:
        print(f"no sitemap match ({len(missing)}):")
        for chip, vram in missing:
            print(f"   {chip} {vram}GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
