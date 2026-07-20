import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery = Celery(
    "audiobooklib",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Ack only after a task finishes so worker restarts (deploys, OOM)
    # redeliver instead of silently dropping in-flight tasks
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # With acks_late, Redis redelivers any task still running after the
    # visibility timeout (default 1h) — a long ingest would then run twice and
    # duplicate every segment. Parallel cleaning keeps us far under this, but
    # raise it so an unusually large PDF can't trip the same wire.
    broker_transport_options={"visibility_timeout": 7200},
    # Split memory-heavy ingest from network-bound synthesis so each can run at
    # its own concurrency. ingest_book balloons large PDFs via PyMuPDF (hundreds
    # of MB per task) and must stay capped low; synthesis is I/O-bound (waiting
    # on the OpenAI TTS API) and can safely run many in parallel. The worker
    # droplet runs one worker per queue with different --concurrency (see
    # docker-compose.worker.yml). Everything not listed defaults to "synth".
    task_routes={
        "app.tasks.ingest_book": {"queue": "ingest"},
        "app.tasks.synthesize_book": {"queue": "synth"},
        "app.tasks.synthesize_segment": {"queue": "synth"},
        "app.tasks.synthesize_narration": {"queue": "synth"},
        "app.tasks.synthesize_segment_audio": {"queue": "synth"},
        "app.tasks.finalize_book": {"queue": "synth"},
    },
    task_default_queue="synth",
)
