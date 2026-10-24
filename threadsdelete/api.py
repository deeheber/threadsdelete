"""Threads API adapter: the only module that talks HTTP (see docs/RESEARCH.md, Contracts)."""

import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx

from threadsdelete.core import Candidate, Category, Operation, parse_timestamp

API_HOST = "graph.threads.com"
Transport = httpx.BaseTransport

REDACTED = "[REDACTED]"

# Categories from docs/RESEARCH.md Contracts > Category: *. Media and carousel posts are POST.
SUPPORTED_CATEGORIES: tuple[Category, ...] = (Category.POST, Category.QUOTE, Category.REPLY)
UNSUPPORTED_CATEGORIES: Mapping[Category, str] = {
    Category.REPOST: "no documented call removes a repost (docs/RESEARCH.md)",
    Category.LIKE: "no documented endpoint lists or removes the owner's likes (docs/RESEARCH.md)",
}
_THREADS_PATH = "me/threads"
_THREADS_FIELDS = "id,timestamp,permalink,owner,media_type,is_quote_post"
_REPLIES_PATH = "me/replies"
_REPLIES_FIELDS = "id,timestamp,permalink,username,is_reply,is_reply_owned_by_me"
_PAGE_SIZE = "100"
_REPOST_TYPE = "REPOST_FACADE"

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


@dataclass(frozen=True)
class Quota:
    remaining: dict[Operation, int]
    window_description: str


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
        self._edges: dict[str, list[dict[str, object]]] = {}
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

    # -- discovery -----------------------------------------------------------------

    def _edge(self, path: str, fields: str) -> list[dict[str, object]]:
        """All records of one list edge, fetched once per client (never mutates)."""
        if path not in self._edges:
            self._edges[path] = self.get_all(path, {"fields": fields, "limit": _PAGE_SIZE})
        return self._edges[path]

    def discover(self, category: Category, identity: Identity) -> tuple[list[Candidate], int]:
        """Candidates of one supported category and the number of records scanned.

        Scanned counts records classified into the category; records of an unsupported
        category found on the same edge (reposts) are counted under POST and not returned.
        """
        if category not in SUPPORTED_CATEGORIES:
            raise ValueError(f"unsupported category: {category}")
        if category is Category.REPLY:
            return self._discover_replies(identity)
        return self._discover_threads(category, identity)

    def _discover_threads(
        self, wanted: Category, identity: Identity
    ) -> tuple[list[Candidate], int]:
        found: list[Candidate] = []
        scanned = 0
        for record in self._edge(_THREADS_PATH, _THREADS_FIELDS):
            media_type = record.get("media_type")
            if not isinstance(media_type, str) or not media_type:
                raise self._fail(ResponseError, "record lacks a media_type; cannot classify")
            if media_type == _REPOST_TYPE:
                if wanted is Category.POST:
                    scanned += 1  # unsupported category: scanned, never a candidate
                continue
            category = Category.QUOTE if record.get("is_quote_post") is True else Category.POST
            if category is not wanted:
                continue
            scanned += 1
            owner = record.get("owner")
            owner_id = owner.get("id") if isinstance(owner, dict) else None
            if owner_id != identity.user_id:
                raise self._fail(OwnershipError, "record owner does not match the account")
            found.append(self._candidate(category, record))
        return found, scanned

    def _discover_replies(self, identity: Identity) -> tuple[list[Candidate], int]:
        found: list[Candidate] = []
        records = self._edge(_REPLIES_PATH, _REPLIES_FIELDS)
        for record in records:
            if record.get("is_reply_owned_by_me") is not True:
                raise self._fail(OwnershipError, "reply is not confirmed as owned by the account")
            if record.get("username") != identity.username:
                raise self._fail(OwnershipError, "reply username does not match the account")
            found.append(self._candidate(Category.REPLY, record))
        return found, len(records)

    def _candidate(self, category: Category, record: dict[str, object]) -> Candidate:
        target_id = record["id"]
        permalink = record.get("permalink")
        assert isinstance(target_id, str)  # validated by get_all
        return Candidate(
            category=category,
            target_id=target_id,
            action_at=parse_timestamp(record.get("timestamp")),
            permalink=permalink if isinstance(permalink, str) and permalink else None,
        )

    # -- quota and removal ---------------------------------------------------------

    def get_quota(self, identity: Identity) -> Quota:
        """Remaining deletions from threads_publishing_limit (RESEARCH: Quota inspection)."""
        body = self._get(
            f"{identity.user_id}/threads_publishing_limit",
            {"fields": "delete_quota_usage,delete_config"},
        )
        data = body.get("data")
        entry = data[0] if isinstance(data, list) and data else None
        if not isinstance(entry, dict):
            raise self._fail(ResponseError, "quota response has no data entry")
        usage = entry.get("delete_quota_usage")
        config = entry.get("delete_config")
        total = config.get("quota_total") if isinstance(config, dict) else None
        duration = config.get("quota_duration") if isinstance(config, dict) else None
        if not (_is_count(usage) and _is_count(total) and _is_count(duration) and duration):
            raise self._fail(ResponseError, "quota response fields are missing or malformed")
        assert isinstance(usage, int) and isinstance(total, int) and isinstance(duration, int)
        hours, rest = divmod(duration, 3600)
        window = f"rolling {hours} hours" if hours and not rest else f"rolling {duration} seconds"
        return Quota(remaining={Operation.DELETE: max(total - usage, 0)}, window_description=window)

    def remove(self, candidate: Candidate) -> None:
        """One DELETE attempt, never retried. Returns only on a validated success body."""
        if candidate.operation is not Operation.DELETE:
            raise ValueError(f"unsupported operation: {candidate.operation}")
        try:
            response = self._send("DELETE", candidate.target_id, {})
        except httpx.TimeoutException, httpx.TransportError:
            raise self._fail(
                UnknownOutcomeError, "removal request failed; outcome unknown"
            ) from None
        except httpx.HTTPError:
            raise self._fail(
                UnknownOutcomeError, "removal request not completed; outcome unknown"
            ) from None
        if response.is_success:
            self._check_removal_body(response, candidate.target_id)
            return
        error = self._classify(response)
        if isinstance(error, (AuthError, QuotaExceededError)):
            raise error
        if response.status_code < 500 and _is_error_body(response):
            raise self._fail(ItemError, f"removal rejected ({error})")
        raise self._fail(UnknownOutcomeError, f"removal outcome unknown ({error})")

    def _check_removal_body(self, response: httpx.Response, target_id: str) -> None:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
            raise self._fail(UnknownOutcomeError, "removal response body not recognised")
        if body["success"] is False:
            raise self._fail(ItemError, "removal reported success: false")
        deleted = body.get("deleted_id")
        if deleted is not None and deleted != target_id:
            raise self._fail(UnknownOutcomeError, "removal response names a different item")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_error_body(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and isinstance(body.get("error"), dict)
