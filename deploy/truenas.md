# Running the harvest on TrueNAS SCALE

The NAS only harvests and pushes. It does not build the site — Cloudflare Pages
does that on push. So the NAS needs **python3 (stdlib only) and git**, nothing
else. No pip installs, no jinja2, no build tooling on the appliance.

## What actually runs

```
/mnt/<pool>/apps/komper/tools/update.sh
   └── python3 tools/harvest.py --pages 1 --xkom-pages 4
   └── git add data && git commit && git push     → Cloudflare rebuilds
```

Five requests per run. Four runs a day.

## 1. Stage the repo on a dataset

Anything that survives upgrades — a pool dataset, not `/root` or `/etc`.

```bash
mkdir -p /mnt/<pool>/apps
cd /mnt/<pool>/apps
git clone git@github.com:997volt/komper.git
```

If `git` is missing on the host, that is the moment to reconsider: the
alternative is committing through the GitHub API, which puts a token back into
the picture. Check first:

```bash
which git python3 && python3 -V
```

## 2. Give the NAS write access — a deploy key, not your account key

On GitHub: **Settings → Deploy keys → Add deploy key**, paste a public key
generated on the NAS, and tick **Allow write access**.

A deploy key is scoped to this one repository and nothing else. Generate it as
the user the cron job will run as:

```bash
ssh-keygen -t ed25519 -C "komper-truenas" -f /root/.ssh/komper_deploy -N ""
cat /root/.ssh/komper_deploy.pub
```

Point SSH at it in `/root/.ssh/config`:

```
Host github.com
  IdentityFile /root/.ssh/komper_deploy
  IdentitiesOnly yes
```

Verify before scheduling anything:

```bash
ssh -T git@github.com          # expect "Hi 997volt! ..."
cd /mnt/<pool>/apps/komper && git push
```

## 3. Add the Cron Job in the UI

**System Settings → Advanced → Cron Jobs → Add**

| Field | Value |
|---|---|
| Description | komper harvest |
| Command | `/mnt/<pool>/apps/komper/tools/update.sh >> /mnt/<pool>/apps/komper-harvest.log 2>&1` |
| Run As User | `root` (or whoever owns the key) |
| Schedule | Custom: `7 */6 * * *` |

Four runs a day, off the hour. TrueNAS cron does not offer randomised jitter, so
the script's own `--delay` spacing governs politeness between requests; if you
want jitter between runs, schedule at an odd minute as above and leave it.

## 4. Test it before trusting it

Use **Run Now** in the Cron Jobs UI, then:

```bash
tail -20 /mnt/<pool>/apps/komper-harvest.log
cd /mnt/<pool>/apps/komper && git log --oneline -2
```

Expect `prices updated and pushed`, a new commit, and a Pages deployment within
a minute. Then check the site footer timestamp moved.

## Caveats specific to an appliance

- **Upgrades.** Cron jobs live in the TrueNAS config database and survive; the
  script lives on a dataset and survives; anything you `apt install` on the host
  may not. That is the argument for keeping the dependency list at python3+git.
- **PATH.** The job runs with a minimal environment. `update.sh` exports an
  explicit PATH and resolves its own directory, so it does not depend on `$HOME`.
- **Run-as user.** Run as root with the key in `/root/.ssh`, or create a
  dedicated user and keep the clone and the key owned by it. Do not mix: a root
  cron job against a user-owned clone usually fails on file permissions.
- **Secrets hygiene.** `/root/.ssh` is on the boot environment in some setups —
  make sure the deploy key is regenerable rather than precious. It is: one click
  to add another.

## Alternative: a container

If you would rather isolate this from the host, TrueNAS SCALE 24.10+ runs Docker
apps. A minimal image with `python3`, `git`, `openssh-client` and a cron or
`sleep` loop, with the dataset mounted at `/repo`, does the same job. It is more
moving parts for the same five requests — worth it only if you already run other
custom apps and want one more.
