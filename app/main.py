import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.db import init_db, SessionLocal, DiscEvent
from app.disc_watcher import start_watcher_thread, scan_current_state, get_known_drives

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Disc-O-Matic")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup():
    init_db()
    scan_current_state()
    start_watcher_thread()


@app.get("/api/drives")
def list_drives():
    return JSONResponse(get_known_drives())


def _event_to_dict(e: DiscEvent) -> dict:
    return {
        "id": e.id,
        "device": e.device,
        "detected_at": e.detected_at.isoformat(),
        "media_type": e.media_type,
        "disc_label": e.disc_label,
        "match_status": e.match_status,
        "matches": [
            {
                "source": m.source,
                "external_id": m.external_id,
                "title": m.title,
                "year": m.year,
                "score": m.score,
                "extra": m.extra,
            }
            for m in e.matches
        ],
    }


@app.get("/api/events")
def list_events():
    session = SessionLocal()
    try:
        events = (
            session.query(DiscEvent)
            .order_by(DiscEvent.detected_at.desc())
            .limit(50)
            .all()
        )
        return JSONResponse([_event_to_dict(e) for e in events])
    finally:
        session.close()


@app.get("/")
def index(request: Request):
    session = SessionLocal()
    try:
        events = (
            session.query(DiscEvent)
            .order_by(DiscEvent.detected_at.desc())
            .limit(50)
            .all()
        )
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "events": events, "watched_devices": get_known_drives()},
        )
    finally:
        session.close()

