"""Request ids, access logging, and background job status."""

from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import sentry_sdk
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from invoice_machine.utils import utc_now

logger = logging.getLogger("invoice_machine.access")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# A caller-supplied id is echoed only when it is short and log-safe.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class RequestIdFilter(logging.Filter):
    """Stamp every record with the current request or job id."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestIdMiddleware:
    """Assign an id per request, echo it in X-Request-ID, and log one access line."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if _SAFE_ID.fullmatch(supplied) else new_request_id()
        token = request_id_var.set(request_id)
        # The isolation scope is opened outside this stack, so the tag survives
        # until Sentry captures the event.
        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
        status = 0
        started = time.perf_counter()

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # Logged and answered here, while the id is still set; the re-raise
            # lets the server's error middleware record the traceback.
            logger.exception("unhandled error")
            if status == 0:
                response = JSONResponse(
                    {"detail": "Internal server error", "request_id": request_id},
                    status_code=500,
                )
                await response(scope, receive, send_with_id)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            path = scope.get("path", "")
            level = logging.DEBUG if path == "/health" else logging.INFO
            logger.log(level, "%s %s -> %s %.1fms", scope.get("method"), path, status, elapsed_ms)
            request_id_var.reset(token)


async def run_job(
    jobs: dict[str, dict[str, Any]], name: str, job: Callable[[], Awaitable[Any]]
) -> bool:
    """Run a background job under its own id, record the outcome, and report success.

    A failure is logged here, while the job id is still set, and never propagates.
    """
    token = request_id_var.set(f"job-{new_request_id()}")
    started = utc_now()
    entry = jobs.setdefault(name, {"runs": 0, "failures": 0})
    entry["last_started_at"] = started.isoformat()
    entry["runs"] += 1
    try:
        await job()
    except Exception as exc:
        entry["failures"] += 1
        entry["last_error"] = f"{type(exc).__name__}: {exc}"
        entry["last_error_at"] = utc_now().isoformat()
        logging.getLogger("invoice_machine.jobs").error("%s failed: %s", name, exc, exc_info=True)
        return False
    else:
        entry["last_ok_at"] = utc_now().isoformat()
        entry["last_error"] = None
        return True
    finally:
        entry["last_duration_ms"] = round((utc_now() - started).total_seconds() * 1000, 1)
        request_id_var.reset(token)
