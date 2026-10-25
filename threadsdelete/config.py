"""Environment parsing and validation. Standard library only; takes a mapping, no globals."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_DRY_RUN = True
DEFAULT_DAYS_AGO = 90
LOG_LEVEL = "INFO"
API_VERSION = "v1.0"
MAX_DAYS_AGO = 36500

# ⚠️ ASSUMPTION defaults (SPEC section 5); tuned in P2-06 and P3-04.
DEFAULT_MAX_DELETIONS_PER_RUN = 100
HTTP_TIMEOUT_SECONDS = 30.0
MAX_READ_RETRIES = 3
MAX_RETRY_WAIT_SECONDS = 60.0

ENV_KEYS = (
    "DRY_RUN",
    "DAYS_AGO",
    "THREADS_ACCESS_TOKEN",
    "THREADS_USER_ID",
    "MAX_DELETIONS_PER_RUN",
)

_INT = re.compile(r"[0-9]+")


class ConfigError(ValueError):
    """Invalid configuration. Messages name keys and rules, never values."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Config:
    dry_run: bool
    days_ago: int
    access_token: str = field(repr=False)
    user_id: str
    max_deletions_per_run: int


def load_config(env: Mapping[str, str]) -> Config:
    """Validate every key before any network activity; report all problems at once."""
    problems: list[str] = []

    def raw(key: str) -> str | None:
        value = env.get(key)
        if value is None or not value.strip():
            return None
        return value.strip()

    def required(key: str, rule: str, pattern: re.Pattern[str] | None) -> str:
        value = raw(key)
        if value is None:
            problems.append(f"{key} is required")
            return ""
        if pattern is not None and not pattern.fullmatch(value):
            problems.append(f"{key} must {rule}")
            return ""
        return value

    def boolean(key: str, default: bool) -> bool:
        value = raw(key)
        if value is None:
            return default
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        problems.append(f"{key} must be true or false (case-insensitive)")
        return default

    def integer(key: str, default: int, maximum: int | None = None) -> int:
        value = raw(key)
        if value is None:
            return default
        if not _INT.fullmatch(value):
            problems.append(f"{key} must be a non-negative integer (digits only)")
            return default
        number = int(value)
        if maximum is not None and number > maximum:
            problems.append(f"{key} must be at most {maximum}")
            return default
        return number

    dry_run = boolean("DRY_RUN", DEFAULT_DRY_RUN)
    days_ago = integer("DAYS_AGO", DEFAULT_DAYS_AGO, MAX_DAYS_AGO)

    access_token = required("THREADS_ACCESS_TOKEN", "be set", None)
    user_id = required("THREADS_USER_ID", "be ASCII digits only", _INT)
    max_deletions = integer("MAX_DELETIONS_PER_RUN", DEFAULT_MAX_DELETIONS_PER_RUN)

    if problems:
        raise ConfigError(problems)
    return Config(
        dry_run=dry_run,
        days_ago=days_ago,
        access_token=access_token,
        user_id=user_id,
        max_deletions_per_run=max_deletions,
    )
