"""Bounded watchlist READs and non-sensitive error classification."""
from contextlib import contextmanager
from contextvars import ContextVar
import re
import time

ITEM_RETRY_DELAYS = (2, 5)
RECOVERY_RETRY_DELAYS = (15, 45, 120)
RUN_TIMEOUT_SECONDS = 480
RECOVERY_WINDOW_SECONDS = 900
REUSE_MAX_AGE_SECONDS = 900
INITIAL_MAX_READ_CALLS = 600
RECOVERY_MAX_READ_CALLS = 60
READ_MIN_INTERVAL_SECONDS = 1.0
CLAIM_LEASE_SECONDS = 600
_budget = ContextVar('watchlist_read_budget', default=None)


class SnapshotReadStopped(RuntimeError):
    pass


class SnapshotReadBudget:
    def __init__(self, *, checkpoint, reserve, wait, monotonic=time.monotonic,
                 min_interval=READ_MIN_INTERVAL_SECONDS):
        self.checkpoint, self.reserve, self.wait = checkpoint, reserve, wait
        self.monotonic, self.min_interval = monotonic, min_interval
        self.last_read = None
        self.stopped = None

    def before_read(self):
        try:
            self.checkpoint()
            if self.last_read is not None:
                delay = self.min_interval - (self.monotonic() - self.last_read)
                if delay > 0:
                    self.wait(delay)
            self.checkpoint()
            self.reserve()  # Persist before HTTP; crashes cannot reset usage.
            self.last_read = self.monotonic()
        except SnapshotReadStopped as exc:
            self.stopped = str(exc)
            raise


def check_snapshot_read():
    budget = _budget.get()
    if budget is not None:
        budget.before_read()


@contextmanager
def snapshot_read_budget(budget):
    token = _budget.set(budget)
    try:
        yield
    finally:
        _budget.reset(token)


def safe_snapshot_error(error, *, stage):
    """Inspect errors in memory; persist only fixed codes and known types."""
    text = str(error or '')
    details = getattr(error, 'details', {}) or {}
    details = details if isinstance(details, dict) else {}
    known_types = ('TimeoutError', 'Timeout', 'ReadTimeout', 'ConnectTimeout', 'ConnectionError',
                   'ConnectionResetError', 'KisApiError', 'ValueError', 'RuntimeError',
                   'SnapshotReadStopped')
    kind = type(error).__name__ if isinstance(error, BaseException) else text.split(':', 1)[0]
    kind = kind if kind in known_types else 'UnknownError'
    provider_type = details.get('error_type')
    if provider_type in known_types:
        kind = provider_type
    status = details.get('http_status')
    if not isinstance(status, int) or isinstance(status, bool) or not 400 <= status <= 599:
        match = re.search(r'(?:http_status|HTTP|status_code)[\s=:]+([45]\d\d)\b', text)
        status = int(match[1]) if match else None
    lower = text.lower()
    if isinstance(error, SnapshotReadStopped):
        allowed = {'snapshot_cancelled', 'snapshot_timeout', 'snapshot_lease_lost',
                   'snapshot_read_budget_exhausted', 'snapshot_recovery_deadline'}
        reason = text if text in allowed else 'snapshot_stopped'
        retryable = reason in {'snapshot_cancelled', 'snapshot_timeout'}
    elif kind in {'TimeoutError', 'Timeout', 'ReadTimeout', 'ConnectTimeout'} or 'timed out' in lower:
        reason, retryable = 'transport_timeout', True
    elif kind in {'ConnectionError', 'ConnectionResetError'} or 'connection reset' in lower:
        reason, retryable = 'transport_connection_failed', True
    elif status == 429 or details.get('msg_cd') in {'EGW00201', 'EGW00215'} or any(x in text for x in ('EGW00201', 'EGW00215')):
        reason, retryable = 'provider_rate_limited', True
    elif status is not None and status >= 500:
        reason, retryable = 'provider_unavailable', True
    elif status in {401, 403}:
        reason, retryable = 'provider_auth_rejected', False
    elif stage == 'indicator':
        reason, retryable = 'indicator_invalid', False
    else:
        reason, retryable = 'unclassified_read_failure', False
    return {'stage': stage, 'reason_code': reason, 'exception_type': kind,
            'http_status': status, 'retryable': retryable}


def sanitize_snapshot_error(details, *, stage):
    """Accept only classifier output, even when a custom data adapter is used."""
    reasons = {
        'transport_timeout', 'transport_connection_failed', 'provider_rate_limited',
        'provider_unavailable', 'provider_auth_rejected', 'indicator_invalid', 'indicator_input_unavailable',
        'unclassified_read_failure', 'snapshot_cancelled', 'snapshot_timeout',
        'snapshot_lease_lost', 'snapshot_read_budget_exhausted',
        'snapshot_recovery_deadline', 'snapshot_stopped', 'worker_interrupted',
    }
    kinds = {'TimeoutError', 'Timeout', 'ReadTimeout', 'ConnectTimeout', 'ConnectionError',
             'ConnectionResetError', 'KisApiError', 'ValueError', 'RuntimeError',
             'SnapshotReadStopped', 'UnknownError'}
    reason = details.get('reason_code')
    if reason not in reasons:
        return safe_snapshot_error(None, stage=stage)
    status = details.get('http_status')
    return {'stage': stage, 'reason_code': reason,
            'exception_type': details.get('exception_type') if details.get('exception_type') in kinds else 'UnknownError',
            'http_status': status if type(status) is int and 400 <= status <= 599 else None,
            'retryable': reason in {'transport_timeout', 'transport_connection_failed',
                'provider_rate_limited', 'provider_unavailable', 'worker_interrupted',
                'snapshot_cancelled', 'snapshot_timeout', 'indicator_input_unavailable'}}
