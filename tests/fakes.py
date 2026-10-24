"""Offline fakes. Import as `from tests.fakes import ...` so the socket guard loads."""

import json
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from threadsdelete.api import ThreadsClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VERSION = "v1.0"

Reply = httpx.Response | Exception


def load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return result


def json_response(
    body: object, status: int = 200, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def error_response(code: int, status: int = 400, message: str = "error") -> httpx.Response:
    body = {"error": {"message": message, "type": "OAuthException", "code": code}}
    return json_response(body, status)


class FakeThreadsApi:
    """Maps (method, path) to a queue of responses or exceptions and records every request."""

    def __init__(self, version: str = VERSION) -> None:
        self.version = version
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self._queues: dict[tuple[str, str], deque[Reply]] = {}
        self._sticky: set[tuple[str, str]] = set()
        self.transport = httpx.MockTransport(self._handle)

    def add(self, method: str, path: str, *replies: Reply, repeat: bool = False) -> None:
        key = (method.upper(), path.strip("/"))
        self._queues.setdefault(key, deque()).extend(replies)
        if repeat:
            self._sticky.add(key)

    def paths(self, method: str | None = None) -> list[str]:
        return [self._path(r) for r in self.requests if method is None or r.method == method]

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and self._path(r) == path.strip("/")]

    def _path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(f"/{self.version}/").strip("/")

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, self._path(request))
        queue = self._queues.get(key)
        if not queue:
            raise RuntimeError(f"unexpected request {key[0]} {key[1]}")
        reply = queue[0] if key in self._sticky and len(queue) == 1 else queue.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_client(fake: FakeThreadsApi, **overrides: Any) -> ThreadsClient:
    settings: dict[str, Any] = {
        "access_token": "fake-token-value",
        "api_version": fake.version,
        "timeout_seconds": 1.0,
        "max_read_retries": 2,
        "max_retry_wait_seconds": 5.0,
        "read_only": True,
        "transport": fake.transport,
        "sleep": fake.sleeps.append,
    }
    settings.update(overrides)
    return ThreadsClient(**settings)


def fixture_api(quota: bool = True) -> FakeThreadsApi:
    """Account example_owner with the synthetic fixtures: 5 eligible items at 90 days."""
    fake = FakeThreadsApi()
    fake.add("GET", "me", json_response(load_fixture("me.json")))
    fake.add(
        "GET",
        "me/threads",
        json_response(load_fixture("threads_page1.json")),
        json_response(load_fixture("threads_page2.json")),
    )
    fake.add("GET", "me/replies", json_response(load_fixture("replies.json")))
    if quota:
        fake.add(
            "GET", "1000001/threads_publishing_limit", json_response(load_fixture("quota.json"))
        )
    return fake
