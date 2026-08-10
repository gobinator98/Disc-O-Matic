import logging
import os

import requests

logger = logging.getLogger("discomatic.tmdb")

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def _search(kind: str, query: str, limit: int = 5) -> list[dict]:
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not set, skipping %s search for %r", kind, query)
        return []

    try:
        resp = requests.get(
            f"{TMDB_BASE_URL}/search/{kind}",
            params={"api_key": TMDB_API_KEY, "query": query},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("TMDB %s search failed for query %r", kind, query)
        return []

    results = resp.json().get("results", [])[:limit]
    out = []
    for r in results:
        if kind == "movie":
            title = r.get("title")
            date = r.get("release_date") or ""
        else:
            title = r.get("name")
            date = r.get("first_air_date") or ""
        out.append({
            "external_id": str(r.get("id")),
            "title": title,
            "year": date[:4] if date else None,
            "score": r.get("popularity"),
            "extra": {"overview": r.get("overview")},
        })
    return out


def search_movie(query: str, limit: int = 5) -> list[dict]:
    return _search("movie", query, limit)


def search_tv(query: str, limit: int = 5) -> list[dict]:
    return _search("tv", query, limit)


def label_to_query(disc_label: str) -> str:
    """Disc volume labels are typically underscore/dash-separated,
    all-caps, and often carry junk like disc numbers - turn that into
    something closer to normal title text for a text search."""
    text = disc_label.replace("_", " ").replace("-", " ")
    return " ".join(text.split()).title()

