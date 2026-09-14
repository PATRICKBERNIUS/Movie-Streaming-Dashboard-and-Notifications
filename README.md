# Reel Ledger + Weekly Streaming Alert

Two pieces that share the same GitHub repo as their source of truth:

- **`app.py`** — a Streamlit dashboard where you keep your movie watchlist
  and streaming subscriptions, and check what's available right now.
- **`check_availability.py`** — runs automatically every Friday via GitHub
  Actions and sends a phone notification for anything on your list that's
  currently streaming on your services.

Both read and write the same two files in this repo (`movies.json` and
`streaming_services.json`), so there's one list, not two.

## One-time setup

### 1. Create the repo

Create a GitHub repo (private is fine) and upload everything in this
folder, keeping the structure — `.github/workflows/` and `.streamlit/`
both matter as exact paths.

### 2. Get a free ntfy topic for your phone

- Install the "ntfy" app (iOS or Android — free, no account needed).
- In the app, subscribe to a topic name you make up — make it long and
  unguessable, since anyone who knows it can send you notifications,
  e.g. `alex-movie-alerts-9f3k2`.

### 3. Get a free Watchmode API key

Register at https://api.watchmode.com/ and copy your key from the
dashboard.

### 4. Create a GitHub personal access token

This lets both the dashboard and (optionally) your own scripts read and
write `movies.json` / `streaming_services.json` in this one repo.

- Go to https://github.com/settings/tokens?type=beta → "Generate new token"
- Scope it to **only this repository**
- Permissions → Repository permissions → **Contents: Read and write**
- Copy the token — GitHub only shows it once.

### 5. Add secrets for the weekly Actions script

Repo → Settings → Secrets and variables → Actions → New repository secret:

- `WATCHMODE_API_KEY` — your Watchmode key
- `NTFY_TOPIC` — your ntfy topic name

(Your subscribed services are *not* a secret — they live in
`streaming_services.json`, edited from the dashboard.)

### 6. Run the dashboard

**Locally:**
```
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your real values
streamlit run app.py
```

`.streamlit/config.toml` sets the app's color theme — it's already
committed and safe (no secrets in it), so it applies automatically.

**Optional — movie posters:** add a free `TMDB_API_KEY` to your secrets
(sign up at https://www.themoviedb.org/settings/api). Without it, the
dashboard works exactly the same, just without poster thumbnails.

**Hosted (so it's just a URL, no laptop required)** — deploy for free on
[Streamlit Community Cloud](https://streamlit.io/cloud):
- Connect your GitHub repo, pick `app.py` as the entry point.
- In the app's Settings → Secrets, paste the same key/value pairs from
  `secrets.toml.example` (real values, not the placeholders).
- Your dashboard gets a public-ish URL (unlisted, not indexed) you can
  open from your phone anytime — no browser storage involved, since the
  token and API key live in Streamlit's server-side secrets instead.

### 7. Test the weekly script manually

Repo → Actions tab → "Weekly streaming availability check" → "Run workflow."
Check the run logs, and check your phone for the ntfy notification.

## Why two separate credentials stores?

`WATCHMODE_API_KEY` and `GITHUB_TOKEN` are real credentials, so they live
in secrets in *two* places that never talk to each other automatically:
GitHub Actions secrets (for the Friday script) and Streamlit secrets (for
the dashboard). Your movie list and services aren't sensitive, so they
live as plain files in the repo instead, kept in sync by both programs
reading/writing the same files.

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
