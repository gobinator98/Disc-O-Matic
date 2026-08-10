import logging

from app.celery_app import celery_app
from app.db import SessionLocal, DiscEvent, DiscMatch
from app import tmdb_client, musicbrainz_client

logger = logging.getLogger("discomatic.tasks")

# Media types we actually know how to look up right now. Data/mixed discs
# and "unknown" are left unmatched rather than guessed at.
VIDEO_TYPES = {"dvd", "bluray"}
AUDIO_TYPES = {"audio_cd"}


@celery_app.task(name="discomatic.match_disc", bind=True, max_retries=2, default_retry_delay=15)
def match_disc_task(self, disc_event_id: int):
    session = SessionLocal()
    try:
        event = session.get(DiscEvent, disc_event_id)
        if event is None:
            logger.warning("match_disc_task: DiscEvent %s no longer exists", disc_event_id)
            return

        event.match_status = "pending"
        session.commit()

        candidates: list[dict] = []

        try:
            if event.media_type in VIDEO_TYPES:
                candidates.extend(_match_video(event))
            elif event.media_type in AUDIO_TYPES:
                candidates.extend(_match_audio(event))
            else:
                event.match_status = "unmatched"
                session.commit()
                return
        except Exception:
            logger.exception("Matching failed for disc_event %s", disc_event_id)
            event.match_status = "error"
            session.commit()
            raise self.retry(exc=None)

        for c in candidates:
            session.add(DiscMatch(disc_event_id=event.id, **c))

        event.match_status = "matched" if candidates else "no_candidates"
        session.commit()
        logger.info(
            "match_disc_task: disc_event=%s media_type=%s -> %d candidate(s)",
            disc_event_id, event.media_type, len(candidates),
        )
    finally:
        session.close()


def _match_video(event: DiscEvent) -> list[dict]:
    if not event.disc_label:
        return []
    query = tmdb_client.label_to_query(event.disc_label)
    results = []
    for m in tmdb_client.search_movie(query):
        results.append({"source": "tmdb_movie", **m})
    for t in tmdb_client.search_tv(query):
        results.append({"source": "tmdb_tv", **t})
    return results


def _match_audio(event: DiscEvent) -> list[dict]:
    disc_id, releases = musicbrainz_client.match_audio_cd(event.device)
    if disc_id and not event.raw_properties.get("_musicbrainz_disc_id"):
        # Stash the computed disc ID on the event for visibility/debugging.
        event.raw_properties = {**(event.raw_properties or {}), "_musicbrainz_disc_id": disc_id}
    return [{"source": "musicbrainz", **r} for r in releases]

