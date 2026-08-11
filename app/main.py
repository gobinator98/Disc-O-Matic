import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import init_db, SessionLocal, DiscEvent
from app.disc_watcher import start_watcher_thread, scan_current_state, get_known_drives
from app.sample_data import SAMPLE_JOBS, SAMPLE_JOB_DETAIL, SAMPLE_HISTORY, SAMPLE_HISTORY_DETAIL

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Disc-O-Matic")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

APP_VERSION = "v0.1.0"

# Active/Completed job counts require rip-execution tracking (workflow
# steps 7+), which isn't implemented yet — only disc detection and
# auto-match (steps 1-2) are real. Placeholder values until that lands.
ACTIVE_JOBS_SAMPLE = 1
COMPLETED_JOBS_SAMPLE = 8

MEDIA_LABELS = {
    "dvd": "DVD", "bluray": "Blu-ray", "audio_cd": "Audio CD",
    "mixed_cd": "Mixed CD", "data_cd": "Data Disc", "unknown": "Unknown Disc",
}
MEDIA_ICONS = {"dvd": "ti-movie", "bluray": "ti-movie", "audio_cd": "ti-disc", "mixed_cd": "ti-disc"}


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


def _build_drive_view(device: str, event: DiscEvent | None) -> dict:
    if event is None or event.media_type == "no_media":
        return {
            "device": device, "icon": "ti-player-eject", "title": device, "title_class": "muted",
            "media_label": None, "matched_line": None, "extra_line": "No disc inserted",
            "badge_text": None, "badge_class": None, "invalid": False, "has_link": False,
        }

    media_type = event.media_type
    if media_type in ("data_cd", "unknown"):
        return {
            "device": device, "icon": "ti-alert-triangle", "title": "Invalid Disc", "title_class": "invalid",
            "media_label": None, "matched_line": None,
            "extra_line": "Eject and insert an audio CD, DVD, or Blu-ray",
            "badge_text": "invalid disc", "badge_class": "invalid", "invalid": True, "has_link": False,
        }

    if event.disc_label:
        title, title_class = event.disc_label, ""
    elif media_type in ("audio_cd", "mixed_cd"):
        title, title_class = "Audio CD", "muted"
    else:
        title, title_class = "(No disc label)", "muted"

    best_match = event.matches[0] if event.matches else None
    matched_line = None
    if best_match:
        matched_line = f"Matched: {best_match.title}" + (f" ({best_match.year})" if best_match.year else "")

    if event.match_status == "matched":
        badge_text, badge_class = "matched", "matched"
    elif event.match_status == "pending":
        badge_text, badge_class = "queued — awaiting match", "queued"
    elif event.match_status in ("no_candidates", "unmatched", "error"):
        badge_text, badge_class = "needs attention", "warn"
    else:
        badge_text, badge_class = None, None

    return {
        "device": device, "icon": MEDIA_ICONS.get(media_type, "ti-disc"), "title": title, "title_class": title_class,
        "media_label": MEDIA_LABELS.get(media_type), "matched_line": matched_line, "extra_line": None,
        "badge_text": badge_text, "badge_class": badge_class, "invalid": False,
        "has_link": badge_text is not None,
    }


@app.get("/")
def dashboard(request: Request):
    session = SessionLocal()
    try:
        drive_paths = get_known_drives()
        drives = []
        pending_count = 0
        needs_attention_count = 0
        for device in drive_paths:
            event = (
                session.query(DiscEvent)
                .filter(DiscEvent.device == device)
                .order_by(DiscEvent.detected_at.desc())
                .first()
            )
            if event:
                if event.match_status == "pending":
                    pending_count += 1
                if event.match_status in ("no_candidates", "unmatched", "error") and event.media_type not in ("data_cd", "unknown"):
                    needs_attention_count += 1
            drives.append(_build_drive_view(device, event))

        return templates.TemplateResponse("dashboard.html", {
            "request": request, "active_page": "dashboard",
            "drives": drives,
            "pending_count": pending_count,
            "needs_attention_count": needs_attention_count,
            "active_jobs_sample": ACTIVE_JOBS_SAMPLE,
            "completed_jobs_sample": COMPLETED_JOBS_SAMPLE,
            "app_version": APP_VERSION,
        })
    finally:
        session.close()


@app.get("/jobs")
def jobs(request: Request):
    return templates.TemplateResponse("jobs.html", {
        "request": request, "active_page": "jobs",
        "jobs": SAMPLE_JOBS,
        "drive_count": len(get_known_drives()),
        "app_version": APP_VERSION,
    })


@app.get("/jobs/{job_id}")
def job_detail(request: Request, job_id: str):
    # Only one sample job is fully fleshed out today; any id shows it until
    # real per-job tracking exists.
    job = dict(SAMPLE_JOB_DETAIL)
    job["id"] = job_id
    return templates.TemplateResponse("job_detail.html", {
        "request": request, "active_page": "jobs", "job": job,
    })


@app.get("/history")
def history(request: Request):
    return templates.TemplateResponse("history.html", {
        "request": request, "active_page": "history",
        "history": SAMPLE_HISTORY,
    })


@app.get("/history/{history_id}")
def history_detail(request: Request, history_id: str):
    h = SAMPLE_HISTORY_DETAIL if history_id == SAMPLE_HISTORY_DETAIL["id"] else dict(SAMPLE_HISTORY_DETAIL, id=history_id)
    return templates.TemplateResponse("history_detail.html", {
        "request": request, "active_page": "history", "h": h,
    })


@app.get("/settings")
def settings(request: Request):
    raw_key = os.environ.get("TMDB_API_KEY", "")
    masked_key = (raw_key[:4] + "…" + raw_key[-4:]) if len(raw_key) > 8 else "(not set)"
    return templates.TemplateResponse("settings.html", {
        "request": request, "active_page": "settings",
        "tmdb_key_masked": masked_key,
        "makemkv_version": "installed (see container image)",
        "app_version": APP_VERSION,
    })
