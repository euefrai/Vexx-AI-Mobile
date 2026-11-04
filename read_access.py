"""Process-local coordination of anonymous public reads; no completed-body cache."""
import copy
import hashlib
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit


def retry_after(headers):
    value = str(headers.get('Retry-After', '') if headers else '').strip()
    if not value or len(value) > 128:
        return None
    if value.isascii() and value.isdigit():
        return min(int(value), 31_536_000)
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            return None
        return max(0, min((stamp - datetime.now(timezone.utc)).total_seconds(), 31_536_000))
    except (ValueError, TypeError, OverflowError):
        return None


class Deferred(ValueError):
    def __init__(self, reason, code='rede', status=None, delay=0):
        super().__init__('Leitura adiada: ' + reason)
        self.access_reason = reason
        self.codigo = code
        self.http = status
        self.retry_after = max(0, delay)


class Coordinator:
    def __init__(self, per_origin=2, max_entries=256):
        self.per_origin = per_origin
        self.max_entries = max_entries
        self._condition = threading.Condition()
        self._active = {}
        self._flights = {}
        self._deferred = OrderedDict()

    def _remember(self, key, exc):
        status = getattr(exc, 'http', None)
        reason = getattr(exc, 'access_reason', '')
        delay = getattr(exc, 'retry_after', None)
        origin_wide = status in (429, 503)
        if origin_wide:
            delay = max(1, delay) if delay is not None else (30 if status == 429 else 5)
        elif status in (401, 403) or reason == 'challenge_required':
            delay = 15  # A protected URL must not disable unrelated public pages.
        else:
            return
        if not isinstance(delay, (int, float)) or not math.isfinite(delay) or delay <= 0:
            return
        scope = key[0] if origin_wide else key
        self._deferred[scope] = (time.monotonic() + delay, reason,
                                 getattr(exc, 'codigo', 'rede'), status)
        self._deferred.move_to_end(scope)
        while len(self._deferred) > self.max_entries:
            self._deferred.popitem(last=False)

    def run(self, url, signature, timeout, operation, *, namespace=None, cancelled=None):
        deadline = time.monotonic() + timeout
        parsed = urlsplit(url)
        origin = (namespace, parsed.scheme, parsed.hostname,
                  parsed.port or (443 if parsed.scheme == 'https' else 80))
        key = (origin, hashlib.sha256(url.encode()).hexdigest(), signature)
        with self._condition:
            while True:
                if cancelled and cancelled():
                    raise Deferred('cancelled', 'cancelada')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Deferred('read_budget_exhausted')
                # Reuse an ongoing request only, never its completed cached body.
                flight = self._flights.get(key)
                if flight is not None:
                    while not flight['done']:
                        if cancelled and cancelled():
                            raise Deferred('cancelled', 'cancelada')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise Deferred('read_budget_exhausted')
                        self._condition.wait(min(remaining, 0.05))
                    if cancelled and cancelled():
                        raise Deferred('cancelled', 'cancelada')
                    if time.monotonic() >= deadline:
                        raise Deferred('read_budget_exhausted')
                    if flight.get('error') is not None:
                        raise copy.copy(flight['error']).with_traceback(None)
                    return flight['result']
                for scope in (origin, key):
                    deferred = self._deferred.get(scope)
                    if deferred:
                        until, reason, code, status = deferred
                        if until > time.monotonic():
                            raise Deferred(reason, code, status, until - time.monotonic())
                        del self._deferred[scope]
                if (self._active.get(origin, 0) < self.per_origin
                        and len(self._flights) < min(16, self.max_entries)):
                    flight = {'done': False}
                    self._flights[key] = flight
                    self._active[origin] = self._active.get(origin, 0) + 1
                    break
                self._condition.wait(min(remaining, 0.05))
        try:
            result = operation(max(0.001, deadline - time.monotonic()))
            with self._condition:
                flight['result'] = result
            if cancelled and cancelled():
                raise Deferred('cancelled', 'cancelada')
            return result
        except BaseException as exc:
            with self._condition:
                if 'result' not in flight:
                    flight['error'] = exc
                    self._remember(key, exc)
            raise
        finally:
            with self._condition:
                flight['done'] = True
                self._flights.pop(key, None)
                self._active[origin] -= 1
                if not self._active[origin]:
                    del self._active[origin]
                self._condition.notify_all()


public_reads = Coordinator()
