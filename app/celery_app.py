import os

from celery import Celery

REDIS_HOST = os.environ.get("REDIS_HOST", "disco-matic-redis")
BROKER_URL = f"redis://{REDIS_HOST}:6379/0"

celery_app = Celery("discomatic", broker=BROKER_URL, backend=BROKER_URL)
celery_app.conf.task_default_queue = "discomatic"
# The worker process only imports this module (via `celery -A app.celery_app
# worker`) - without this it never loads app.tasks, so the @celery_app.task
# decorator in there never runs and every task shows up as "unregistered".
celery_app.conf.imports = ("app.tasks",)

