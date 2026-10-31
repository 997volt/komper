#!/usr/bin/env bash
# Harvest prices, commit, push. The push triggers the Cloudflare Pages build,
# so this one script is the whole update loop.
#
# Intended for a timer on a machine with a normal internet connection - never in
# CI, where the requests would come from a datacenter.
#
# Every run commits, because data/prices.json carries a scrape timestamp and that
# timestamp is meaningful: it is what the page shows as "prices from ...". At four
# runs a day that is ~120 builds a month against the 500 the free plan allows.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 tools/harvest.py --pages 1 --details 14

git add data
git commit -q -m "prices: $(date -u '+%Y-%m-%d %H:%M UTC')"
# the remote may have moved if a human pushed meanwhile
git pull --rebase --autostash -q || true
git push -q
echo "prices updated and pushed"
