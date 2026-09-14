"""
Reel Ledger — Streamlit dashboard

A movie watchlist that shows where each title currently streams, kept in
sync with the same GitHub repo the weekly notification script reads from.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Configure secrets in .streamlit/secrets.toml (see secrets.toml.example)
or, if deployed on Streamlit Community Cloud, in the app's Settings ->
Secrets panel.
"""

import base64
import json
import time
from datetime import datetime

import requests
import streamlit as st

st.set_page_config(page_title="Reel Ledger", page_icon="🎬", layout="centered")

# ---------------------------------------------------------------------------
# Config — pulled from Streamlit secrets, never typed into the page itself
# ---------------------------------------------------------------------------
WATCHMODE_API_KEY = st.secrets.get("WATCHMODE_API_KEY", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_OWNER = st.secrets.get("GITHUB_OWNER", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")
MOVIES_PATH = st.secrets.get("MOVIES_PATH", "movies.json")
SERVICES_PATH = st.secrets.get("SERVICES_PATH", "streaming_services.json")
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")  # optional — enables posters

COMMON_SERVICES = [
    "Netflix", "Amazon Prime Video", "Max", "Hulu", "Disney+",
    "Apple TV+", "Paramount+", "Peacock", "Starz", "AMC+", "Tubi", "Crunchyroll",
]

MISSING_CONFIG = [
    name for name, val in [
        ("WATCHMODE_API_KEY", WATCHMODE_API_KEY),
        ("GITHUB_TOKEN", GITHUB_TOKEN),
        ("GITHUB_OWNER", GITHUB_OWNER),
        ("GITHUB_REPO", GITHUB_REPO),
    ] if not val
]

# ---------------------------------------------------------------------------
# GitHub content helpers
# ---------------------------------------------------------------------------

def gh_headers():
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}


def gh_url(path):
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


class GithubError(Exception):
    pass


def load_from_github(path, default):
    try:
        res = requests.get(gh_url(path), headers=gh_headers(), timeout=20)
    except requests.RequestException:
        raise GithubError("Couldn't reach GitHub — check your internet connection and try again.")
    if res.status_code == 404:
        return default, None
    if res.status_code in (401, 403):
        raise GithubError(
            f"GitHub rejected the request for {path} (status {res.status_code}). "
            "Check that GITHUB_TOKEN is valid and still scoped to this repo with Contents: Read and write."
        )
    if not res.ok:
        raise GithubError(f"GitHub returned an unexpected error loading {path} (status {res.status_code}).")
    data = res.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    try:
        return json.loads(content), data["sha"]
    except json.JSONDecodeError:
        raise GithubError(f"{path} in the repo doesn't look like valid JSON.")


def save_to_github(path, obj, sha, message):
    content = base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("utf-8")
    body = {"message": message, "content": content}
    if sha:
        body["sha"] = sha
    try:
        res = requests.put(gh_url(path), headers=gh_headers(), json=body, timeout=20)
    except requests.RequestException:
        raise GithubError("Couldn't reach GitHub to save your change — check your connection and try again.")
    if not res.ok:
        err = res.json().get("message", "") if res.headers.get("content-type", "").startswith("application/json") else ""
        raise GithubError(f"GitHub save to {path} failed ({res.status_code}). {err}")
    return res.json()["content"]["sha"]


# ---------------------------------------------------------------------------
# Watchmode helpers
# ---------------------------------------------------------------------------

class WatchmodeError(Exception):
    pass


def _watchmode_get(url, params):
    try:
        res = requests.get(url, params=params, timeout=20)
    except requests.RequestException:
        raise WatchmodeError("Couldn't reach Watchmode — check your connection.")
    if res.status_code == 401:
        raise WatchmodeError("Watchmode rejected the API key — check WATCHMODE_API_KEY.")
    if res.status_code == 429:
        raise WatchmodeError("Hit Watchmode's rate limit — wait a bit before checking again.")
    if not res.ok:
        raise WatchmodeError(f"Watchmode returned an error (status {res.status_code}).")
    return res.json()


def search_title(title, year=None):
    data = _watchmode_get(
        "https://api.watchmode.com/v1/search/",
        {"apiKey": WATCHMODE_API_KEY, "search_field": "name", "search_value": title},
    )
    results = [r for r in data.get("title_results", []) if r.get("type") == "movie"]
    if not results:
        return None
    if year:
        for r in results:
            if str(r.get("year")) == str(year):
                return r
    return results[0]


def get_sources(watchmode_id):
    return _watchmode_get(
        f"https://api.watchmode.com/v1/title/{watchmode_id}/sources/",
        {"apiKey": WATCHMODE_API_KEY},
    )


def matching_services(sources, my_services):
    matches = set()
    for s in sources:
        if s.get("type") != "sub":
            continue
        name = (s.get("name") or "").lower()
        for svc in my_services:
            svc_l = svc.lower().replace("+", "")
            if svc_l in name or name in svc.lower():
                matches.add(svc)
    return matches


def check_movie_availability(title, year, my_services):
    match = search_title(title, year)
    if not match:
        return []
    sources = get_sources(match["id"])
    return sorted(matching_services(sources, my_services))


# ---------------------------------------------------------------------------
# TMDB poster helper (optional — skipped gracefully if no key configured)
# ---------------------------------------------------------------------------

def get_poster_url(title, year):
    if not TMDB_API_KEY:
        return None
    cache_key = f"{title}|{year}"
    if cache_key in st.session_state.posters:
        return st.session_state.posters[cache_key]
    try:
        params = {"api_key": TMDB_API_KEY, "query": title}
        if year:
            params["year"] = year
        res = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=15)
        if not res.ok:
            st.session_state.posters[cache_key] = None
            return None
        results = res.json().get("results", [])
        if not results or not results[0].get("poster_path"):
            st.session_state.posters[cache_key] = None
            return None
        url = f"https://image.tmdb.org/t/p/w154{results[0]['poster_path']}"
        st.session_state.posters[cache_key] = url
        return url
    except requests.RequestException:
        st.session_state.posters[cache_key] = None
        return None


# ---------------------------------------------------------------------------
# Session state — load once per session from GitHub (source of truth)
# ---------------------------------------------------------------------------

def load_state():
    movies, movies_sha = load_from_github(MOVIES_PATH, [])
    services_doc, services_sha = load_from_github(SERVICES_PATH, {"services": []})
    st.session_state.movies = movies
    st.session_state.movies_sha = movies_sha
    st.session_state.services = services_doc.get("services", [])
    st.session_state.services_sha = services_sha
    st.session_state.availability = st.session_state.get("availability", {})
    st.session_state.posters = st.session_state.get("posters", {})


if MISSING_CONFIG:
    st.error(
        "**Missing configuration:** " + ", ".join(f"`{c}`" for c in MISSING_CONFIG) + "\n\n"
        "Add these in `.streamlit/secrets.toml` (local) or the app's Settings → Secrets panel "
        "(Streamlit Community Cloud). See `secrets.toml.example` for the full list."
    )
    st.stop()

if "movies" not in st.session_state:
    with st.spinner("Loading your list from GitHub…"):
        try:
            load_state()
        except GithubError as e:
            st.error(f"**Couldn't load your list.** {e}")
            st.stop()

# ---------------------------------------------------------------------------
# UI — header & stats
# ---------------------------------------------------------------------------

st.title("🎬 Reel Ledger")

movies = st.session_state.movies
availability = st.session_state.availability


def status_of(movie):
    key = f"{movie['title']}|{movie.get('year')}"
    avail = availability.get(key)
    if avail is None:
        return "unchecked"
    return "available" if len(avail) > 0 else "unavailable"


counts = {"available": 0, "unavailable": 0, "unchecked": 0}
for m in movies:
    counts[status_of(m)] += 1

col1, col2, col3 = st.columns(3)
col1.metric("Tracked", len(movies))
col2.metric("🟢 Available", counts["available"])
col3.metric("Not yet", counts["unavailable"] + counts["unchecked"])

if st.button("🔄 Refresh from GitHub", use_container_width=False):
    with st.spinner("Reloading…"):
        try:
            load_state()
            st.toast("Reloaded from GitHub.")
        except GithubError as e:
            st.error(str(e))
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Add movie
# ---------------------------------------------------------------------------

with st.form("add_movie_form", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    new_title = c1.text_input("Add a movie", placeholder="Title")
    new_year = c2.text_input("Year", placeholder="e.g. 2024")
    submitted = c3.form_submit_button("Add", use_container_width=True)
    if submitted:
        if not new_title.strip():
            st.warning("Enter a title before adding.")
        elif any(m["title"].lower() == new_title.strip().lower() for m in movies):
            st.warning(f"'{new_title.strip()}' is already on your list.")
        else:
            try:
                movies.append({"title": new_title.strip(), "year": new_year.strip() or None})
                st.session_state.movies_sha = save_to_github(
                    MOVIES_PATH, movies, st.session_state.movies_sha,
                    f"Add '{new_title.strip()}' via Reel Ledger",
                )
                st.success(f"Added {new_title.strip()}.")
                st.rerun()
            except GithubError as e:
                movies.pop()  # roll back the local append since the save failed
                st.error(f"**Couldn't save.** {e}")

st.divider()

# ---------------------------------------------------------------------------
# Check availability
# ---------------------------------------------------------------------------

check_col, sort_col = st.columns([2, 1])
with check_col:
    check_clicked = st.button("✅ Check availability for everything", type="primary")
with sort_col:
    sort_by = st.selectbox("Sort by", ["Title (A–Z)", "Year (newest first)"], label_visibility="collapsed")

if check_clicked:
    if not st.session_state.services:
        st.warning("Pick at least one streaming service below before checking.")
    elif not movies:
        st.info("Add a movie first.")
    else:
        progress = st.progress(0.0, text="Starting…")
        total = len(movies)
        errors = []
        for i, m in enumerate(movies):
            key = f"{m['title']}|{m.get('year')}"
            progress.progress(i / total, text=f"Checking {m['title']}…")
            try:
                availability[key] = check_movie_availability(m["title"], m.get("year"), st.session_state.services)
            except WatchmodeError as e:
                availability[key] = None
                errors.append(f"{m['title']}: {e}")
            time.sleep(0.3)
        progress.progress(1.0, text="Done.")
        time.sleep(0.2)
        progress.empty()
        if errors:
            st.error("Some lookups failed:\n\n" + "\n".join(f"- {e}" for e in errors))
        st.rerun()

st.divider()


def sort_key(m):
    if sort_by == "Year (newest first)":
        try:
            return -int(m.get("year") or 0)
        except (TypeError, ValueError):
            return 0
    return (m.get("title") or "").lower()


def render_movie_card(movie, muted=False):
    key = f"{movie['title']}|{movie.get('year')}"
    avail = availability.get(key)
    poster_url = get_poster_url(movie["title"], movie.get("year"))

    with st.container(border=True):
        cols = st.columns([1, 4, 1]) if poster_url else st.columns([5, 1])
        if poster_url:
            img_col, text_col, remove_col = cols
            img_col.image(poster_url, width=60)
        else:
            text_col, remove_col = cols

        with text_col:
            year_str = f" ({movie['year']})" if movie.get("year") else ""
            title_md = f"**{movie['title']}**{year_str}"
            text_col.markdown(f":gray[{title_md}]" if muted else title_md)
            if avail is None:
                text_col.caption("Not checked yet")
            elif len(avail) == 0:
                text_col.caption("Not on your services")
            else:
                text_col.markdown(" ".join(f"`{s}`" for s in avail))

        with remove_col:
            if remove_col.button("✕", key=f"remove_{key}", help="Remove from list"):
                try:
                    idx = next(i for i, mv in enumerate(movies) if mv["title"] == movie["title"] and mv.get("year") == movie.get("year"))
                    removed = movies.pop(idx)
                    availability.pop(key, None)
                    st.session_state.movies_sha = save_to_github(
                        MOVIES_PATH, movies, st.session_state.movies_sha,
                        f"Remove '{removed['title']}' via Reel Ledger",
                    )
                    st.rerun()
                except GithubError as e:
                    movies.insert(idx, removed)
                    st.error(f"**Couldn't remove.** {e}")


if not movies:
    st.info("🎞️ Nothing on the ledger yet — add a title above to start tracking it.")
else:
    available_movies = sorted([m for m in movies if status_of(m) == "available"], key=sort_key)
    unavailable_movies = sorted([m for m in movies if status_of(m) == "unavailable"], key=sort_key)
    unchecked_movies = sorted([m for m in movies if status_of(m) == "unchecked"], key=sort_key)

    if available_movies:
        st.subheader(f"🟢 Available now ({len(available_movies)})")
        for m in available_movies:
            render_movie_card(m)

    if unavailable_movies:
        st.subheader(f"⚪ Not on your services ({len(unavailable_movies)})")
        for m in unavailable_movies:
            render_movie_card(m, muted=True)

    if unchecked_movies:
        st.subheader(f"❔ Not checked yet ({len(unchecked_movies)})")
        for m in unchecked_movies:
            render_movie_card(m, muted=True)

st.divider()

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

with st.expander("⚙️ Your streaming subscriptions"):
    st.caption("Changes here sync straight to streaming_services.json in the repo.")
    cols = st.columns(3)
    new_services = list(st.session_state.services)
    changed = False
    for i, svc in enumerate(COMMON_SERVICES):
        col = cols[i % 3]
        checked = col.checkbox(svc, value=svc in st.session_state.services, key=f"svc_{svc}")
        if checked and svc not in new_services:
            new_services.append(svc)
            changed = True
        elif not checked and svc in new_services:
            new_services.remove(svc)
            changed = True
    if changed:
        try:
            st.session_state.services_sha = save_to_github(
                SERVICES_PATH, {"services": new_services}, st.session_state.services_sha,
                "Update streaming services via Reel Ledger",
            )
            st.session_state.services = new_services
            st.rerun()
        except GithubError as e:
            st.error(f"**Couldn't save your services.** {e}")

if not TMDB_API_KEY:
    st.caption("💡 Add a free `TMDB_API_KEY` to secrets to show movie posters.")

st.caption(f"Connected to {GITHUB_OWNER}/{GITHUB_REPO} · last loaded {datetime.now().strftime('%H:%M:%S')}")
