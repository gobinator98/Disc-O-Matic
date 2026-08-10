import logging
import threading

import pyudev

from app.db import SessionLocal, DiscEvent

logger = logging.getLogger("discomatic.disc_watcher")

# Drives currently known to be optical devices (populated by discovery +
# add/remove events). Not used to *filter* insert/change handling - that's
# decided from each event's own ID_CDROM property - just used to answer
# "what drives does this box have right now" for the UI/API.
_known_drives_lock = threading.Lock()
_known_drives: set[str] = set()


def get_known_drives() -> list[str]:
    with _known_drives_lock:
        return sorted(_known_drives)


def _is_optical_drive(device: pyudev.Device) -> bool:
    # ID_CDROM=1 is set by udev on the drive itself (a capability flag),
    # independent of whether media is currently inserted - this is how
    # udisks2 and friends detect "this is an optical drive" too, and it
    # works the same whether there's 1 drive or 10, USB or SATA.
    return device.properties.get("ID_CDROM") == "1"


def classify_media(props: dict) -> str:
    """Classify inserted media using the udev cdrom_id properties the
    kernel/udev already populate on insert - no custom probing needed.
    """
    if props.get("ID_CDROM_MEDIA") != "1":
        return "no_media"

    track_audio = int(props.get("ID_CDROM_MEDIA_TRACK_COUNT_AUDIO") or 0)
    track_data = int(props.get("ID_CDROM_MEDIA_TRACK_COUNT_DATA") or 0)
    is_bd = props.get("ID_CDROM_MEDIA_BD") == "1"
    is_dvd = props.get("ID_CDROM_MEDIA_DVD") == "1"
    is_cd = props.get("ID_CDROM_MEDIA_CD") == "1"
    fs_type = props.get("ID_FS_TYPE")

    if is_bd:
        return "bluray"
    if is_dvd:
        return "dvd"
    if is_cd:
        if track_audio > 0 and track_data == 0:
            return "audio_cd"
        if track_data > 0 and track_audio == 0:
            return "data_cd"
        if track_audio > 0 and track_data > 0:
            return "mixed_cd"
        if fs_type:
            return "data_cd"
    return "unknown"


def _record_event(device: str, props: dict):
    media_type = classify_media(props)
    label = props.get("ID_FS_LABEL")

    session = SessionLocal()
    try:
        event = DiscEvent(
            device=device,
            media_type=media_type,
            disc_label=label,
            raw_properties=dict(props),
        )
        session.add(event)
        session.commit()
        logger.info("Recorded disc event: device=%s media_type=%s label=%s", device, media_type, label)
        event_id = event.id
    finally:
        session.close()

    if media_type != "no_media":
        from app.tasks import match_disc_task
        match_disc_task.delay(event_id)


def _handle_udev_event(device: pyudev.Device):
    devnode = device.device_node
    if not devnode:
        return

    if device.action == "add":
        if _is_optical_drive(device):
            with _known_drives_lock:
                _known_drives.add(devnode)
            logger.info("New optical drive detected: %s", devnode)
            # A drive that shows up already loaded (e.g. hot-plugged with a
            # disc already in it) should be picked up immediately too.
            if device.properties.get("ID_CDROM_MEDIA") == "1":
                _record_event(devnode, dict(device.properties))
        return

    if device.action == "remove":
        with _known_drives_lock:
            _known_drives.discard(devnode)
        logger.info("Optical drive removed: %s", devnode)
        return

    if device.action == "change" and _is_optical_drive(device):
        with _known_drives_lock:
            _known_drives.add(devnode)
        _record_event(devnode, dict(device.properties))


def scan_current_state():
    """On startup, discover every optical drive present right now
    (regardless of count) and record any that already have media inserted,
    so we don't miss a disc that was in the tray before the app came up.
    """
    context = pyudev.Context()
    found = []
    for device in context.list_devices(subsystem="block"):
        if not _is_optical_drive(device):
            continue
        devnode = device.device_node
        if not devnode:
            continue
        found.append(devnode)
        with _known_drives_lock:
            _known_drives.add(devnode)
        if device.properties.get("ID_CDROM_MEDIA") == "1":
            _record_event(devnode, dict(device.properties))

    logger.info("Startup discovery found %d optical drive(s): %s", len(found), found)


def start_watcher_thread():
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="block")

    def _run():
        for device in iter(monitor.poll, None):
            try:
                _handle_udev_event(device)
            except Exception:
                logger.exception("Error handling udev event for %s", device.device_node)

    thread = threading.Thread(target=_run, name="discomatic-disc-watcher", daemon=True)
    thread.start()
    logger.info("Disc watcher thread started (auto-discovering drives, no fixed list)")
    return thread

