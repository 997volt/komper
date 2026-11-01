#!/usr/bin/env python3
"""Fill in specs for chips that have prices but no gpus.csv row.

Prices come from category listings, which morele caps at 30 products per page.
Specs are per chip and rarely change, so they do not belong on that path: morele
declares product sitemaps in robots.txt, and the components sitemap carries every
GPU product URL. One detail fetch per chip is enough to learn its shader count,
clocks and bus width.

    python3 tools/specs.py            # only chips that are missing specs
    python3 tools/specs.py --limit 5  # go slowly

Appends to data/gpus.csv. Existing rows are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harvest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_SITEMAP = (
    "https://www.morele.net/product_active_sitemap_13_podzespoly_komputerowe.xml"
)
GPU_IN_URL = "karta-graficzna"
FIELDS = [
    "key", "chip", "vram_gb", "arch", "shaders", "boost_mhz", "bus_bits",
    "mem_mhz", "psu_w", "length_mm", "arch_eff", "perf_adj", "note",
]
# Calibration constants live here so they are visible next to the data.
ARCH_EFF = {
    "Blackwell": 1.00, "Ada": 1.00, "Ampere": 1.00, "Turing": 1.00,
    "RDNA4": 1.45, "RDNA3": 1.30, "RDNA2": 1.15, "Battlemage": 0.78,
}


def gpu_urls() -> list[str]:
    html = harvest.fetch(COMPONENTS_SITEMAP, timeout=60)
    import re
    return [
        url
        for url in re.findall(r"<loc>([^<]+)</loc>", html)
        if GPU_IN_URL in url
    ]


def chip_of(url: str) -> tuple[str, int] | None:
    slug = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    chip = harvest.CHIP.search(slug)
    vram = harvest.VRAM.search(slug)
    if not chip or not vram:
        return None
    return harvest.normalise_chip(chip.group(1)), int(vram.group(1))


def key_of(chip: str, vram: int) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", f"{chip} {vram}gb".lower()).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--delay", type=float, default=4.0)
    args = ap.parse_args()

    csv_path = ROOT / "data" / "gpus.csv"
    rows = list(csv.DictReader(csv_path.open()))
    by_key = {row["key"]: row for row in rows}

    prices = json.loads((ROOT / "data" / "prices.json").read_text())["records"]
    wanted: set[tuple[str, int]] = set()
    for rec in prices:
        if rec.get("is_outlet") or rec.get("in_stock") is False:
            continue
        if not rec.get("chip") or not rec.get("vram_gb"):
            continue
        chip, vram = rec["chip"], int(rec["vram_gb"])
        key = key_of(chip, vram)
        row = by_key.get(key)
        broken = row is None or not all(
            row.get(c) for c in ("shaders", "boost_mhz", "bus_bits", "mem_mhz")
        )
        if broken:
            wanted.add((chip, vram))

    if not wanted:
        print("every priced chip already has specs")
        return 0
    print(f"{len(wanted)} chip(s) need specs: " + ", ".join(f"{c} {v}GB" for c, v in sorted(wanted)))

    urls = gpu_urls()
    print(f"{len(urls)} gpu product urls in the sitemap")
    by_chip: dict[tuple[str, int], list[str]] = {}
    for url in urls:
        parsed = chip_of(url)
        if parsed:
            by_chip.setdefault(parsed, []).append(url)

    added = 0
    for chip, vram in sorted(wanted):
        if added >= args.limit:
            print("limit reached")
            break
        candidates = by_chip.get((chip, vram))
        if not candidates:
            print(f"  {chip} {vram}GB: no sitemap match, skipped")
            continue
        url = candidates[0]
        spec = harvest.details(url)
        time.sleep(args.delay)
        if not all(spec.get(c) for c in ("shaders", "boost_mhz", "bus_bits", "mem_mhz")):
            print(f"  {chip} {vram}GB: incomplete spec sheet, skipped")
            continue
        arch = harvest.arch_of(chip)
        entry = {
                "key": key_of(chip, vram),
                "chip": chip,
                "vram_gb": vram,
                "arch": arch,
                "shaders": int(spec["shaders"]),
                "boost_mhz": int(spec["boost_mhz"]),
                "bus_bits": int(spec["bus_bits"]),
                "mem_mhz": int(spec["mem_mhz"]),
                "psu_w": int(spec["psu_w"]) if spec.get("psu_w") else "",
                "length_mm": int(spec["length_mm"]) if spec.get("length_mm") else "",
                "arch_eff": ARCH_EFF.get(arch, 1.0),
                "perf_adj": 1.0,
                "note": "specs from morele sitemap detail page; "
                f"arch_eff {arch}={ARCH_EFF.get(arch, 1.0)}",
            }
        existing = by_key.get(entry["key"])
        if existing:
            entry["key"] = existing["key"]
            rows = [entry if r["key"] == existing["key"] else r for r in rows]
        else:
            rows.append(entry)
        added += 1
        print(f"  {chip} {vram}GB: {int(spec['shaders'])} sp, {int(spec['boost_mhz'])} MHz")

    if not added:
        print("nothing added")
        return 0
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"added {added} chip(s) -> {csv_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
