#!/usr/bin/env bash
# Build and publish to Cloudflare Pages, from a machine that has no git access.
# Normal deploys happen automatically: pushing to main triggers a Pages build.
#   ./deploy.sh
# Auth comes from `wrangler login` (stored) or CLOUDFLARE_API_TOKEN in the env.
set -euo pipefail
cd "$(dirname "$0")"

# Canonicals, og:url and the sitemap are absolute, so the build must know the
# host. Change this when the site moves to its own domain.
export SITE_URL="${SITE_URL:-https://komper-git.pages.dev}"

# System npm cache can be root-owned; keep wrangler's cache writable.
export npm_config_cache="${npm_config_cache:-/tmp/npm-cache}"
export npm_config_logs_dir="${npm_config_logs_dir:-/tmp/npm-logs}"

python3 build.py
npx --yes wrangler@latest pages deploy dist --project-name=komper --commit-dirty=true
