from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Hashable

from app.brokers.base import KisApiError

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30
# Two KIS reads can each take 10 seconds on each of three snapshot attempts.
RETRY_SLOT_REPLAY_GRACE_SECONDS = (
    (MAX_ATTEMPTS - 1) * RETRY_DELAY_SECONDS + MAX_ATTEMPTS * 2 * 10 + 15
)
_MAX_PENDING_RETRIES = 128
_RETRY_WORKERS = 4
logger = logging.getLogger(__name__)


class AccountSnapshotReadError(RuntimeError):
    """A fail-closed account snapshot read failure with a preserved cause."""

    failure_stage = "account_snapshot"

    def __init__(self, cause: Exception, *, diagnostics: dict[str, Any] | None = None):
        self.cause = cause
        self.diagnostics = dict(diagnostics or {})
        super().__init__("KIS account snapshot unavailable")


class AccountSnapshotRetryCoordinator:
    """Deduplicated delayed retries dispatched through a bounded worker pool."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: set[Hashable] = set()
        self._capacity = threading.BoundedSemaphore(_MAX_PENDING_RETRIES)
        self._executor = ThreadPoolExecutor(
            max_workers=_RETRY_WORKERS,
            thread_name_prefix="kis-account-snapshot-retry",
        )

    def schedule(
        self,
        key: Hashable,
        callback: Callable[[], int | None],
        *,
        delay_seconds: int = RETRY_DELAY_SECONDS,
    ) -> bool:
        with self._lock:
            if key in self._pending or not self._capacity.acquire(blocking=False):
                return False
            self._pending.add(key)
        self._start_timer(key, callback, delay_seconds)
        return True

    def pending_count(self, scope: str | None = None) -> int:
        with self._lock:
            if scope is None:
                return len(self._pending)
            return sum(
                1
                for key in self._pending
                if isinstance(key, tuple) and key and key[0] == scope
            )

    def _start_timer(
        self,
        key: Hashable,
        callback: Callable[[], int | None],
        delay_seconds: int,
    ) -> None:
        timer = threading.Timer(
            max(0, int(delay_seconds)),
            self._dispatch,
            args=(key, callback),
        )
        timer.daemon = True
        timer.start()

    def _dispatch(self, key: Hashable, callback: Callable[[], int | None]) -> None:
        try:
            self._executor.submit(self._run, key, callback)
        except RuntimeError:
            self._finish(key)

    def _run(self, key: Hashable, callback: Callable[[], int | None]) -> None:
        try:
            delay = callback()
        except Exception as exc:
            # Callback code records scoped diagnostics. Avoid emitting raw broker errors here.
            logger.error(
                "KIS account snapshot retry worker failed scope=%s exception_type=%s",
                _scope_name(key),
                type(exc).__name__,
            )
            delay = None
        if isinstance(delay, int) and delay > 0:
            self._start_timer(key, callback, delay)
        else:
            self._finish(key)

    def _finish(self, key: Hashable) -> None:
        with self._lock:
            if key in self._pending:
                self._pending.remove(key)
                self._capacity.release()


account_snapshot_retry_coordinator = AccountSnapshotRetryCoordinator()


def retryable_kis_account_snapshot_error(error: Exception) -> bool:
    """Return true only for transient KIS read failures, never auth/config errors."""
    chain: list[Exception] = []
    current: Exception | None = error
    visited: set[int] = set()
    while isinstance(current, Exception) and id(current) not in visited:
        visited.add(id(current))
        chain.append(current)
        cause = getattr(current, "cause", None)
        original = getattr(current, "original", None)
        nested = cause if isinstance(cause, Exception) else original
        if not isinstance(nested, Exception):
            nested = current.__cause__
        if not isinstance(nested, Exception):
            break
        current = nested

    from app.services.user_broker_account_service import (
        UserBrokerAuthenticationError,
        UserBrokerEncryptionUnavailableError,
        UserBrokerCredentialsUnavailableError,
        UserBrokerUnavailableError,
    )

    permanent_errors = (
        UserBrokerAuthenticationError,
        UserBrokerEncryptionUnavailableError,
        UserBrokerCredentialsUnavailableError,
    )
    if any(isinstance(item, permanent_errors) for item in chain):
        return False

    transient_types = {
        "timeout",
        "readtimeout",
        "connecttimeout",
        "connectionerror",
        "connectionreseterror",
        "protocolerror",
        "chunkedencodingerror",
        "invalid_json",
        "unexpected_shape",
    }
    temporary_markers = (
        "rate limit",
        "rate-limit",
        "temporarily",
        "temporary",
        "gateway",
        "server error",
        "service unavailable",
        "timed out",
        "timeout",
        "connection reset",
    )
    for item in chain:
        if isinstance(item, UserBrokerUnavailableError):
            details = getattr(item, "details", {}) or {}
            status = _http_status(details)
            if status is not None:
                return status == 429 or status >= 500
            code = str(details.get("msg_cd") or details.get("error_code") or "").strip()
            error_type = str(details.get("error_type") or "").lower()
            response_text = " ".join(
                [str(item)]
                + [str(details.get(key) or "") for key in ("msg1", "msg", "message")]
            ).lower()
            if code in {"EGW00201", "EGW00215"}:
                return True
            if error_type in transient_types:
                return True
            if any(marker in response_text for marker in temporary_markers):
                return True
            # KIS application rejections with a response code are permanent unless
            # they are explicitly classified above as throttling or transient.
            if details.get("msg_cd") or details.get("error_code"):
                continue
        if isinstance(item, KisApiError):
            details = getattr(item, "details", {}) or {}
            status = _http_status(details)
            code = str(details.get("msg_cd") or details.get("error_code") or "").strip()
            error_type = str(details.get("error_type") or "").lower()
            message = str(item).lower()
            if details.get("account_state_retryable") is not None:
                return bool(details.get("account_state_retryable"))
            if details.get("token_expired") or "token expired" in message:
                return False
            if code in {"EGW00201", "EGW00215"} or details.get("kis_rate_limited"):
                return True
            if status is not None:
                return status == 429 or status >= 500
            if error_type in transient_types:
                return True
            if any(marker in message for marker in temporary_markers):
                return True
        if isinstance(item, ValueError) and any(
            marker in str(item).lower()
            for marker in (
                "kis_position_snapshot_invalid",
                "kis_account_snapshot_invalid",
                "positions_invalid_response",
                "account_aggregation_invalid_response",
                "open_orders_invalid_response",
            )
        ):
            return True
        if isinstance(item, (TimeoutError, ConnectionError)):
            return True
        if type(item).__name__.lower() in transient_types:
            return True
    return False


def account_snapshot_failure_diagnostics(
    error: Exception,
    *,
    attempt: int,
    retryable: bool,
) -> dict[str, Any]:
    current: Exception | None = error
    visited: set[int] = set()
    while isinstance(current, Exception) and id(current) not in visited:
        visited.add(id(current))
        nested = getattr(current, "cause", None) or getattr(current, "original", None)
        if not isinstance(nested, Exception):
            nested = current.__cause__
        if not isinstance(nested, Exception):
            break
        current = nested
    return {
        "retry_policy": "kis_account_snapshot",
        "attempts": int(attempt),
        "max_attempts": MAX_ATTEMPTS,
        "retry_delay_seconds": RETRY_DELAY_SECONDS,
        "retryable": bool(retryable),
        "failure_stage": "account_snapshot",
        "final_failure_stage": "account_snapshot",
        "exception_type": type(current).__name__ if current is not None else "RuntimeError",
    }


def _http_status(details: Any) -> int | None:
    if not isinstance(details, dict):
        return None
    try:
        return int(details.get("http_status")) if details.get("http_status") is not None else None
    except (TypeError, ValueError):
        return None


def _scope_name(key: Hashable) -> str:
    if isinstance(key, tuple) and key:
        return str(key[0])[:16]
    return "unknown"
