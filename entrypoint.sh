#!/bin/sh
set -e

echo "Starting udevd..."
/usr/lib/systemd/systemd-udevd --daemon

echo "Triggering coldplug of existing devices..."
udevadm trigger --action=add --subsystem-match=block
udevadm settle --timeout=10

echo "udevd ready, starting Disc-O-Matic..."
exec uvicorn app.main:app --host 0.0.0.0 --port 80
