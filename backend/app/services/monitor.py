"""Live worker/broker introspection for the admin panel.

Everything here goes through the shared Redis broker: the worker droplet has
no public IP, so `celery inspect` broadcasts (answered by the worker over the
broker) and direct Redis reads are the only ways to see it.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import redis

from ..celery_app import celery

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
