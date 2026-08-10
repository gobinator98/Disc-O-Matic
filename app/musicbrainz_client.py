import logging

import discid
import requests

logger = logging.getLogger("discomatic.musicbrainz")

MB_BASE_URL = "https://musicbrainz.org/ws/2"
# MusicBrainz's API usage policy requires an identifying User-Agent.
HEADERS = {"User-Agent": "Disc-O-Matic/0.1 (personal disc-ripping tool)"}


def compute_disc_id(device: str) -> str | None:
    try:
        disc = discid.read(device)
        return disc.id
    except discid.DiscError:
        logger.exception("Failed to read TOC / compute disc ID for %s", device)
        return None


def lookup_release(disc_id: str, limit: int = 5) -> list[dict]:
    try:
        resp = requests.get(
            f"{MB_BASE_URL}/discid/{disc_id}",
            params={"fmt": "json", "inc": "recordings+artist-credits"},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("MusicBrainz lookup failed for disc_id %s", disc_id)
        return []

    data = resp.json()
    releases = data.get("releases", data.get("release", []))
    if isinstance(releases, dict):
        releases = [releases]

    out = []
    for r in releases[:limit]:
        artist_credit = r.get("artist-credit", [])
        artist = artist_credit[0]["name"] if artist_credit else None
        media = r.get("media", [])
        tracks = []
        if media:
            for t in media[0].get("tracks", []):
                tracks.append({"position": t.get("position"), "title": t.get("title")})
        out.append({
            "external_id": r.get("id"),
            "title": r.get("title"),
            "year": (r.get("date") or "")[:4] or None,
            "score": None,  # MusicBrainz discid lookups are exact TOC matches, not scored
            "extra": {"artist": artist, "tracks": tracks},
        })
    return out


def match_audio_cd(device: str) -> tuple[str | None, list[dict]]:
    disc_id = compute_disc_id(device)
    if not disc_id:
        return None, []
    return disc_id, lookup_release(disc_id)

