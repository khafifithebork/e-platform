"""Gunicorn configuration.

Loaded by ``gunicorn -c gunicorn.conf.py config.asgi:application`` in the
container.

This file contains no gunicorn imports on purpose. Gunicorn is Unix-only — it
imports ``fcntl`` — so importing it would make this configuration unreadable on
the Windows machines the project is developed on, and would break the tests
that assert these values. Gunicorn loads this file by execution rather than
import, so plain assignments are all it needs.
"""

import os

# Bind to all interfaces. Inside a container this is the only way the port is
# reachable from the host or a load balancer; the container itself is never
# exposed directly to the internet.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# ASGI workers, not sync workers. The Gunicorn worker class moved out of
# uvicorn core into the separate uvicorn-worker distribution;
# uvicorn.workers.UvicornWorker is deprecated.
worker_class = "uvicorn_worker.UvicornWorker"

# A deliberate constant rather than a CPU-derived formula. The (2 x CPU) + 1
# rule of thumb is for sync workers that block; an async worker spends its time
# waiting on I/O and does not need one process per core. The app tier scales
# horizontally by adding containers, so this stays small and predictable.
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))

# Invariant 5: the app tier writes nothing to local disk. A dash is Gunicorn's
# notation for the standard streams, which the platform collects.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Recycle workers periodically so a slow leak cannot accumulate indefinitely.
# The jitter stops every worker recycling on the same request count and
# dropping a burst of traffic simultaneously.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# Revisit both of these when Server-Sent Events arrive (ADR-002 section 7.4).
# A request timeout and a deliberately long-lived streaming response are in
# direct tension, and the SSE endpoints will need to be excluded or the timeout
# raised.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))

keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
