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


def load_from_github(path, default):
    res = requests.get(gh_url(path), headers=gh_headers(), timeout=20)
    if res.status_code == 404:
        return default, None
    res.raise_for_status()
    data = res.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]


def save_to_github(path, obj, sha, message):
    content = base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("utf-8")
    body = {"message": message, "content": content}
    if sha:
        body["sha"] = sha
    res = requests.put(gh_url(path), headers=gh_headers(), json=body, timeout=20)
    res.raise_for_status()
    return res.json()["content"]["sha"]


# ---------------------------------------------------------------------------
# Watchmode helpers
# ---------------------------------------------------------------------------

def search_title(title, year=None):
    res = requests.get(
        "https://api.watchmode.com/v1/search/",
        params={"apiKey": WATCHMODE_API_KEY, "search_field": "name", "search_value": title},
        timeout=20,
    )
    res.raise_for_status()
    results = [r for r in res.json().get("title_results", []) if r.get("type") == "movie"]
    if not results:
        return None
    if year:
        for r in results:
            if str(r.get("year")) == str(year):
                return r
    return results[0]


def get_sources(watchmode_id):
    res = requests.get(
        f"https://api.watchmode.com/v1/title/{watchmode_id}/sources/",
        params={"apiKey": WATCHMODE_API_KEY},
        timeout=20,
    )
    res.raise_for_status()
    return res.json()


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


if MISSING_CONFIG:
    st.error(
        "Missing configuration: " + ", ".join(MISSING_CONFIG) +
        ". Add these in `.streamlit/secrets.toml` (local) or the app's Secrets "
        "panel (Streamlit Community Cloud). See secrets.toml.example."
    )
    st.stop()

if "movies" not in st.session_state:
    with st.spinner("Loading your list from GitHub…"):
        load_state()

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🎬 Reel Ledger")

col1, col2, col3 = st.columns([1, 1, 1])
col1.metric("Tracked", len(st.session_state.movies))
ready_now = sum(1 for m in st.session_state.movies if st.session_state.availability.get(f"{m['title']}|{m.get('year')}"))
col2.metric("Ready now", ready_now)
if col3.button("🔄 Refresh from GitHub"):
    with st.spinner("Reloading…"):
        load_state()
    st.rerun()

st.divider()

with st.form("add_movie_form", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    new_title = c1.text_input("Add a movie", placeholder="Title")
    new_year = c2.text_input("Year", placeholder="e.g. 2024")
    submitted = c3.form_submit_button("Add", use_container_width=True)
    if submitted and new_title.strip():
        st.session_state.movies.append({"title": new_title.strip(), "year": new_year.strip() or None})
        st.session_state.movies_sha = save_to_github(
            MOVIES_PATH, st.session_state.movies, st.session_state.movies_sha,
            f"Add '{new_title.strip()}' via Reel Ledger",
        )
        st.success(f"Added {new_title.strip()}")
        st.rerun()

st.divider()

if st.button("✅ Check availability for everything", type="primary"):
    if not st.session_state.services:
        st.warning("Pick at least one streaming service below first.")
    else:
        progress = st.progress(0.0, text="Checking…")
        total = len(st.session_state.movies) or 1
        for i, m in enumerate(st.session_state.movies):
            key = f"{m['title']}|{m.get('year')}"
            try:
                st.session_state.availability[key] = check_movie_availability(
                    m["title"], m.get("year"), st.session_state.services
                )
            except requests.RequestException as e:
                st.session_state.availability[key] = []
                st.toast(f"Lookup failed for {m['title']}: {e}")
            progress.progress((i + 1) / total, text=f"Checked {m['title']}")
            time.sleep(0.3)
        progress.empty()
        st.rerun()

if not st.session_state.movies:
    st.info("Nothing on the ledger yet — add a title above.")
else:
    for idx, movie in enumerate(st.session_state.movies):
        key = f"{movie['title']}|{movie.get('year')}"
        avail = st.session_state.availability.get(key)

        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                year_str = f" ({movie['year']})" if movie.get("year") else ""
                st.markdown(f"**{movie['title']}**{year_str}")
                if avail is None:
                    st.caption("Not checked yet")
                elif len(avail) == 0:
                    st.caption("Not on your services")
                else:
                    st.markdown(" ".join(f"`{s}`" for s in avail))
            with c2:
                if st.button("Remove", key=f"remove_{idx}"):
                    st.session_state.movies.pop(idx)
                    st.session_state.availability.pop(key, None)
                    st.session_state.movies_sha = save_to_github(
                        MOVIES_PATH, st.session_state.movies, st.session_state.movies_sha,
                        f"Remove '{movie['title']}' via Reel Ledger",
                    )
                    st.rerun()

st.divider()

with st.expander("⚙️ Your streaming subscriptions"):
    st.caption("Changes here sync straight to streaming_services.json in the repo.")
    cols = st.columns(3)
    changed = False
    new_services = list(st.session_state.services)
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
        st.session_state.services = new_services
        st.session_state.services_sha = save_to_github(
            SERVICES_PATH, {"services": new_services}, st.session_state.services_sha,
            "Update streaming services via Reel Ledger",
        )
        st.rerun()

st.caption(f"Connected to {GITHUB_OWNER}/{GITHUB_REPO} — last loaded {datetime.now().strftime('%H:%M:%S')}")
