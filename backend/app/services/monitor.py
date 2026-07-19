"""Live worker/broker introspection for the admin panel.

Everything here goes through the shared Redis broker: the worker droplet has
no public IP, so `celery inspect` broadcasts (answered by the worker over the
broker) and direct Redis reads are the only ways to see it.
"""
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

import psutil
import redis

from ..celery_app import celery

log = logging.getLogger(__name__)

# We don't route tasks to named queues, so everything waits on Celery's
# default queue, which is a plain Redis list under this key.
QUEUE_NAME = "celery"


def broker_redis() -> redis.Redis:
    """Client for the broker Redis, with short timeouts so an unreachable
    broker degrades the admin panel instead of hanging it."""
    return redis.Redis.from_url(
        os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def worker_stats(timeout: float = 1.0) -> dict:
    """Snapshot of queue depth and every worker that answers an inspect
    broadcast within `timeout` seconds.

    Never raises: broker-down and no-workers both come back as data, because
    those are exactly the states the panel exists to show.
    """
    out = {"broker_reachable": False, "queue_depth": None, "workers": []}

    try:
        r = broker_redis()
        out["queue_depth"] = r.llen(QUEUE_NAME)
        out["broker_reachable"] = True
    except Exception:
        # Broker unreachable — inspect would only block for its timeout.
        return out

    # Each inspect method is a broadcast that blocks for the full timeout, so
    # run the four in parallel (each on its own inspect/connection) to keep the
    # endpoint at ~1x timeout instead of 4x.
    def _inspect(method):
        try:
            return getattr(celery.control.inspect(timeout=timeout), method)() or {}
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        ping, stats, active, reserved = pool.map(
            _inspect, ["ping", "stats", "active", "reserved"]
        )

    now = time.time()
    for name in sorted(ping):
        wstats = stats.get(name) or {}
        pool = wstats.get("pool") or {}
        out["workers"].append(
            {
                "name": name,
                "online": True,
                "concurrency": pool.get("max-concurrency"),
                "uptime_s": wstats.get("uptime"),
                "processed": sum((wstats.get("total") or {}).values()),
                "reserved": len(reserved.get(name) or []),
                "active": [
                    {
                        "task": t.get("name"),
                        "args": t.get("args"),
                        # time_start is the worker's clock; good enough for a
                        # human-scale "running for" display.
                        "runtime_s": (
                            max(0, now - t["time_start"])
                            if t.get("time_start")
                            else None
                        ),
                    }
                    for t in (active.get(name) or [])
                ],
            }
        )
    return out


# --- Host resources -----------------------------------------------------------
#
# The web droplet is read live (this backend runs on it; /proc in a default
# Docker container shows HOST memory/load, which is exactly what we want). The
# worker droplet self-reports: a daemon thread in the Celery worker writes the
# same snapshot to a TTL'd Redis key every HEARTBEAT_INTERVAL_S, so a dead
# worker shows up as a missing/stale key rather than silence.

HOST_METRICS_KEY = "aedo:host_metrics:{host}"
HEARTBEAT_INTERVAL_S = 30
HEARTBEAT_TTL_S = 120  # missing key => no heartbeat for >=2 intervals

# Severity thresholds, shaped by the OOM history: ingest once took the 4GB
# droplets down. Swap filling up is the leading indicator there (the boxes run
# with swap as the OOM cushion), so it trips before raw memory does.
THRESHOLDS = {
    "mem_pct": (80, 92),
    "swap_pct": (50, 80),
    "load_per_cpu": (1.5, 3.0),
}


def collect_host_metrics() -> dict:
    """psutil snapshot of the current host: memory, swap, load, cpus."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    load1, load5, load15 = psutil.getloadavg()
    return {
        "at": time.time(),
        "mem_total_mb": round(mem.total / 2**20),
        "mem_used_mb": round((mem.total - mem.available) / 2**20),
        "mem_pct": round(mem.percent, 1),
        "swap_total_mb": round(swap.total / 2**20),
        "swap_used_mb": round(swap.used / 2**20),
        "swap_pct": round(swap.percent, 1),
        "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
        "cpus": psutil.cpu_count() or 1,
    }


def classify(metrics: dict) -> tuple:
    """(severity, reasons) for one host's metrics against THRESHOLDS."""
    checks = [
        ("mem_pct", metrics["mem_pct"], "memory at {v}%"),
        ("swap_pct", metrics["swap_pct"], "swap at {v}%"),
        (
            "load_per_cpu",
            round(metrics["load"][0] / metrics["cpus"], 2),
            "load {v}x per cpu",
        ),
    ]
    severity, reasons = "ok", []
    for key, value, tmpl in checks:
        warn, crit = THRESHOLDS[key]
        if value >= crit:
            severity = "critical"
            reasons.append(tmpl.format(v=value))
        elif value >= warn:
            if severity == "ok":
                severity = "warn"
            reasons.append(tmpl.format(v=value))
    return severity, reasons


def write_host_metrics(host: str) -> None:
    """One heartbeat: snapshot this host into Redis with a TTL."""
    broker_redis().set(
        HOST_METRICS_KEY.format(host=host),
        json.dumps(collect_host_metrics()),
        ex=HEARTBEAT_TTL_S,
    )


def start_heartbeat(host: str) -> None:
    """Spawn the forever heartbeat thread (daemon: dies with the worker)."""

    def _loop():
        while True:
            try:
                write_host_metrics(host)
            except Exception:
                # Broker briefly unreachable — the TTL'd key going stale IS
                # the signal; just try again next interval.
                log.warning("host-metrics heartbeat failed", exc_info=True)
            time.sleep(HEARTBEAT_INTERVAL_S)

    threading.Thread(target=_loop, name=f"heartbeat-{host}", daemon=True).start()


def resource_report() -> dict:
    """Both hosts' resources + severity; the panel's warning banner source."""
    web = collect_host_metrics()
    web_sev, web_reasons = classify(web)
    hosts = [
        {"host": "web", "online": True, "age_s": 0, "severity": web_sev,
         "reasons": web_reasons, **web},
    ]

    worker_row = {
        "host": "worker",
        "online": False,
        "severity": "warn",
        "reasons": ["no heartbeat in the last 2 minutes"],
    }
    try:
        raw = broker_redis().get(HOST_METRICS_KEY.format(host="worker"))
        if raw:
            metrics = json.loads(raw)
            sev, reasons = classify(metrics)
            worker_row = {
                "host": "worker",
                "online": True,
                "age_s": round(max(0, time.time() - metrics["at"])),
                "severity": sev,
                "reasons": reasons,
                **metrics,
            }
    except Exception:
        worker_row["reasons"] = ["broker unreachable"]
    hosts.append(worker_row)

    order = {"ok": 0, "warn": 1, "critical": 2}
    overall = max((h["severity"] for h in hosts), key=order.get)
    return {"overall": overall, "hosts": hosts}


# --- Logs ---------------------------------------------------------------------
#
# Same asymmetry as resources: the web backend logs to a rotating file on the
# storage volume and the endpoint tails it, while the worker (no public IP)
# ships each formatted line into a capped Redis list the backend reads back.

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
WEB_LOG_PATH = os.path.join("storage", "logs", "web.log")
WORKER_LOG_KEY = "aedo:logs:worker"
WORKER_LOG_MAX = 1000
# How far back from EOF the web tail reads — plenty for the 1000-line cap
# the endpoint enforces, tiny compared to the 2MB rotation size.
TAIL_BYTES = 512_000


class RedisListHandler(logging.Handler):
    """Ships each log line into a capped Redis list; never raises, because a
    broker hiccup must not take the worker down with it."""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(LOG_FORMAT))
        self._redis = broker_redis()

    def emit(self, record):
        try:
            pipe = self._redis.pipeline()
            pipe.lpush(WORKER_LOG_KEY, self.format(record))
            pipe.ltrim(WORKER_LOG_KEY, 0, WORKER_LOG_MAX - 1)
            pipe.execute()
        except Exception:
            pass


def setup_web_file_logging() -> None:
    """Called once from main.py (web process only): mirror root + uvicorn
    access logs into a rotating file the /logs endpoint can tail."""
    os.makedirs(os.path.dirname(WEB_LOG_PATH), exist_ok=True)
    handler = RotatingFileHandler(WEB_LOG_PATH, maxBytes=2_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)
    # uvicorn.access has its own handlers and doesn't propagate to root.
    logging.getLogger("uvicorn.access").addHandler(handler)


def read_web_logs(limit: int) -> list:
    """Last `limit` lines of the web log file (chronological)."""
    try:
        with open(WEB_LOG_PATH, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
        if size > TAIL_BYTES and lines:
            lines = lines[1:]  # first line is almost certainly cut mid-way
        return lines[-limit:]
    except FileNotFoundError:
        return []


def read_worker_logs(limit: int) -> list:
    """Last `limit` shipped worker lines (chronological; list stores newest
    first). Broker-down returns empty rather than 5xx."""
    try:
        raw = broker_redis().lrange(WORKER_LOG_KEY, 0, limit - 1)
        return [line.decode("utf-8", errors="replace") for line in reversed(raw)]
    except Exception:
        return []
