"""Threads API adapter: the only module that talks HTTP (see docs/RESEARCH.md, Contracts)."""

import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx

API_HOST = "graph.threads.com"
Transport = httpx.BaseTransport

REDACTED = "[REDACTED]"

# Error codes from docs/RESEARCH.md Contracts > Errors.
_AUTH_CODES = frozenset({10, 190, 3}) | frozenset(range(200, 300))
_AUTH_STATUSES = frozenset({401, 403})
_THROTTLE_CODES = frozenset({4, 17, 341})
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_RETRY_AFTER = re.compile(r"[0-9]+")
_TOKEN_QUERY = re.compile(r"access_token=[^&\s\"']+")

logger = logging.getLogger("threadsdelete.api")


class ApiError(Exception):
    """Base class. Messages are sanitized before the exception is raised."""


class AuthError(ApiError):
    """Token invalid, expired, or permission missing: stop globally."""


class ResponseError(ApiError):
    """Unexpected status, body, pagination or URL."""


class ReadFailedError(ApiError):
    """Read retry budget exhausted, or Retry-After above the maximum."""


class QuotaExceededError(ApiError):
    """A documented throttling signal."""


class ItemError(ApiError):
    """A known, isolated failure for one item."""


class UnknownOutcomeError(ApiError):
    """A mutation whose result is unknown; never retried, never success."""


class MutationBlockedError(ApiError):
    """A mutation was attempted through a read-only client."""


class OwnershipError(ApiError):
    """Ownership could not be proven; discovery must abort."""


@dataclass(frozen=True)
class Identity:
    user_id: str
    username: str


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every non-empty secret and any access_token query fragment."""
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return _TOKEN_QUERY.sub(f"access_token={REDACTED}", text)


class RedactingFilter(logging.Filter):
    """Redacts secrets from each record's formatted message."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self._secrets)
        record.args = None
        return True


def _error_fields(response: httpx.Response) -> tuple[int | None, int | None]:
    """(code, subcode) from a Graph error body, or (None, None) if absent or malformed."""
    try:
        body = response.json()
    except ValueError:
        return None, None
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None, None
    code = error.get("code")
    sub = error.get("error_subcode")
    return (
        code if isinstance(code, int) and not isinstance(code, bool) else None,
        sub if isinstance(sub, int) and not isinstance(sub, bool) else None,
    )


class ThreadsClient:
    """One httpx client against the trusted API host. Reads retry; mutations never do."""

    def __init__(
        self,
        *,
        access_token: str,
        api_version: str,
        timeout_seconds: float,
        max_read_retries: int,
        max_retry_wait_seconds: float,
        read_only: bool,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = access_token
        self._max_retries = max_read_retries
        self._max_wait = max_retry_wait_seconds
        self._read_only = read_only
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=f"https://{API_HOST}/{api_version}/",
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    @property
    def read_only(self) -> bool:
        return self._read_only

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- internals -----------------------------------------------------------------

    def _fail[E: ApiError](self, kind: type[E], message: str) -> E:
        return kind(redact(message, [self._token]))

    def _classify(self, response: httpx.Response) -> ApiError:
        """Map a non-2xx response to an error class using status and Graph error codes."""
        code, sub = _error_fields(response)
        detail = f"HTTP {response.status_code}"
        if code is not None:
            detail += f", error code {code}" + (f" subcode {sub}" if sub is not None else "")
        if response.status_code in _AUTH_STATUSES or code in _AUTH_CODES:
            return self._fail(AuthError, f"authentication or permission failure ({detail})")
        if response.status_code == 429 or code in _THROTTLE_CODES:
            return self._fail(QuotaExceededError, f"rate limit or quota exhausted ({detail})")
        return self._fail(ResponseError, f"unexpected API response ({detail})")

    def _body(self, response: httpx.Response) -> dict[str, object]:
        try:
            body = response.json()
        except ValueError:
            raise self._fail(ResponseError, "response body is not valid JSON") from None
        if not isinstance(body, dict):
            raise self._fail(ResponseError, "response body is not a JSON object")
        return body

    def _send(self, method: str, path: str, params: Mapping[str, str]) -> httpx.Response:
        """One request attempt. Blocks non-GET on a read-only client before the transport."""
        if self._read_only and method != "GET":
            raise self._fail(MutationBlockedError, f"{method} blocked: client is read-only")
        query = {**params, "access_token": self._token}
        return self._http.request(method, path.lstrip("/"), params=query)

    def _retry_wait(self, response: httpx.Response | None, attempt: int) -> float:
        header = response.headers.get("Retry-After", "").strip() if response is not None else ""
        if _RETRY_AFTER.fullmatch(header):
            wait = float(header)
            if wait > self._max_wait:
                raise self._fail(
                    ReadFailedError, f"Retry-After {header}s exceeds the maximum wait; giving up"
                )
            return wait
        return min(float(2**attempt), self._max_wait)

    def _get(self, path: str, params: Mapping[str, str]) -> dict[str, object]:
        """GET with bounded retries on timeouts, transport errors and transient statuses."""
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            response: httpx.Response | None = None
            reason: str
            try:
                response = self._send("GET", path, params)
            except httpx.TimeoutException:
                reason = "timeout"
            except httpx.TransportError:
                reason = "transport error"
            except httpx.HTTPError:
                raise self._fail(ResponseError, "request could not be sent") from None
            else:
                if response.is_success:
                    return self._body(response)
                error = self._classify(response)
                if isinstance(error, AuthError) or response.status_code not in _RETRY_STATUSES:
                    raise error
                reason = f"HTTP {response.status_code}"
            if attempt + 1 >= attempts:
                raise self._fail(
                    ReadFailedError, f"read failed after {attempts} attempts ({reason})"
                )
            wait = self._retry_wait(response, attempt)
            logger.warning(
                "read attempt %d failed (%s); retrying in %.0fs", attempt + 1, reason, wait
            )
            self._sleep(wait)
        raise self._fail(ReadFailedError, "read failed")  # pragma: no cover

    # -- reads ---------------------------------------------------------------------

    def get_all(self, path: str, params: Mapping[str, str]) -> list[dict[str, object]]:
        """Follow cursor pagination on our own base URL; never request a URL from a response."""
        records: list[dict[str, object]] = []
        query = dict(params)
        seen: set[str] = set()
        while True:
            body = self._get(path, query)
            data = body.get("data")
            if not isinstance(data, list):
                raise self._fail(ResponseError, "page has no data list")
            for item in data:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("id"), str)
                    or not item["id"]
                ):
                    raise self._fail(ResponseError, "page record lacks a string id")
                records.append(item)
            paging = body.get("paging")
            if not isinstance(paging, dict) or not paging.get("next"):
                return records
            cursors = paging.get("cursors")
            after = cursors.get("after") if isinstance(cursors, dict) else None
            if not isinstance(after, str) or not after:
                raise self._fail(ResponseError, "next page offered without an after cursor")
            if after in seen:
                raise self._fail(ResponseError, "pagination cursor repeated")
            seen.add(after)
            query = {**params, "after": after}

    def get_identity(self) -> Identity:
        body = self._get("me", {"fields": "id,username"})
        user_id, username = body.get("id"), body.get("username")
        if not isinstance(user_id, str) or not user_id:
            raise self._fail(ResponseError, "identity response lacks an id")
        if not isinstance(username, str) or not username:
            raise self._fail(ResponseError, "identity response lacks a username")
        return Identity(user_id=user_id, username=username)
