# Weekly Streaming Alert

Checks your watchlist against your streaming subscriptions every Friday and
sends you a phone notification for anything currently available.

## One-time setup (about 10 minutes)

1. **Create a GitHub repo** (private is fine) and upload these files,
   keeping the folder structure (the `.github/workflows/` folder matters).

2. **Get a free ntfy topic for your phone**
   - Install the "ntfy" app (iOS or Android — free, no account needed).
   - In the app, tap "+" and subscribe to a topic name you make up —
     make it long and unguessable since anyone who knows it can send you
     notifications, e.g. `alex-movie-alerts-9f3k2`.
   - That's your `NTFY_TOPIC`.

3. **Get a free Watchmode API key**
   - Register at https://api.watchmode.com/ and copy your API key from
     the dashboard.

4. **Add secrets to your GitHub repo**
   - Repo → Settings → Secrets and variables → Actions → New repository secret.
   - Add two secrets (these are real credentials, so they stay as secrets):
     - `WATCHMODE_API_KEY` — your Watchmode key
     - `NTFY_TOPIC` — the topic name from step 2
   - Your subscribed services are *not* a secret — you'll set those from
     the dashboard in the next step, and they're stored in a plain file
     (`streaming_services.json`) in the repo.

5. **Connect the dashboard to this repo.** Open the Reel Ledger dashboard,
   expand Settings → "GitHub sync", and fill in:
   - Your GitHub username
   - This repo's name (e.g. `streaming-alert`)
   - File path: `movies.json`
   - A **fine-grained personal access token**, scoped to just this repo,
     with "Contents: Read and write" permission — [create one here](https://github.com/settings/tokens?type=beta).

   Once connected, `movies.json` and `streaming_services.json` in this
   repo become the same list and service selection you see in the
   dashboard — adding/removing a movie or ticking a service there
   commits straight to these files. Check the services you subscribe to
   under Settings → "Your streaming subscriptions" — that's what writes
   to `streaming_services.json`.

6. **Test it manually** before waiting for Friday:
   - Repo → Actions tab → "Weekly streaming availability check" → "Run workflow".
   - Check the run logs, and check your phone for the ntfy notification.

## Keeping your list in sync

Once GitHub sync is connected in the dashboard, there's no manual copying:
the dashboard writes directly to `movies.json` in this repo, and the
Friday script reads that same file. If you ever edit `movies.json` by
hand in GitHub instead, the dashboard will pick up those changes the next
time you open it.

## Notification behavior

By default (`ONLY_NEW: "false"` in the workflow) you get a weekly digest
of every title on your list currently available on your services, every
Friday, even if it was already available last week. If you'd rather only
be told about *newly* available titles, change `ONLY_NEW` to `"true"` in
`weekly-check.yml`.

## Changing the schedule

The cron line `0 15 * * 5` means Friday at 15:00 UTC. Adjust the hour to
land at a good time in your own timezone (GitHub Actions cron always
runs in UTC).
