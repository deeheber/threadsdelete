"""Pure candidate types and selection. Standard library only; time is always an argument."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum


class Category(StrEnum):
    POST = "post"
    REPLY = "reply"
    QUOTE = "quote"
    REPOST = "repost"
    LIKE = "like"


class Operation(StrEnum):
    DELETE = "delete"
    UNLIKE = "unlike"


OPERATION_FOR: Mapping[Category, Operation] = {
    Category.POST: Operation.DELETE,
    Category.REPLY: Operation.DELETE,
    Category.QUOTE: Operation.DELETE,
    Category.REPOST: Operation.DELETE,
    Category.LIKE: Operation.UNLIKE,
}


class ExitCode(IntEnum):
    OK = 0
    FAILURE = 1
    CONFIG = 2
    AUTH = 3


class TimestampError(ValueError):
    """A timestamp was malformed or timezone-naive."""


class SelectionError(ValueError):
    """Candidates were ambiguous (conflicting duplicates)."""


@dataclass(frozen=True)
class Candidate:
    category: Category
    target_id: str
    action_at: datetime
    permalink: str | None

    @property
    def operation(self) -> Operation:
        return OPERATION_FOR[self.category]


def parse_timestamp(value: object) -> datetime:
    """Parse an ISO 8601 string carrying a UTC offset into an aware UTC datetime."""
    if not isinstance(value, str) or not value:
        raise TimestampError("timestamp must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise TimestampError("timestamp is not valid ISO 8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimestampError("timestamp has no UTC offset")
    if "T" not in value and " " not in value:
        raise TimestampError("timestamp has no time of day")
    return parsed.astimezone(UTC)


def compute_cutoff(run_started_at: datetime, days_ago: int) -> datetime:
    if run_started_at.tzinfo is None or run_started_at.utcoffset() is None:
        raise ValueError("run_started_at must be timezone-aware")
    return run_started_at.astimezone(UTC) - timedelta(days=days_ago)


def is_eligible(candidate: Candidate, cutoff: datetime) -> bool:
    return candidate.action_at <= cutoff


def select_eligible(candidates: Iterable[Candidate], cutoff: datetime) -> list[Candidate]:
    """Eligible candidates, deduplicated by (operation, id), sorted deterministically."""
    chosen: dict[tuple[Operation, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.operation, candidate.target_id)
        seen = chosen.get(key)
        if seen is not None:
            if seen.action_at != candidate.action_at:
                raise SelectionError(
                    f"{candidate.operation} {candidate.target_id}: conflicting action times"
                )
            continue
        chosen[key] = candidate
    eligible = [c for c in chosen.values() if is_eligible(c, cutoff)]
    return sorted(eligible, key=lambda c: (c.action_at, c.category.value, c.target_id))


@dataclass
class CategoryCounts:
    scanned: int = 0
    eligible: int = 0
    would_remove: int = 0
    removed: int = 0
    failed: int = 0
    unknown_outcome: int = 0
    deferred: int = 0


@dataclass
class RunSummary:
    counts: dict[Category, CategoryCounts]
    discovery_complete: bool = True
    auth_failed: bool = False
    notes: list[str] = field(default_factory=list)
