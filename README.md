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
