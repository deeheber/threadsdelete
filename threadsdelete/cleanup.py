"""Identity check, complete discovery, selection, budget split and the report."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TextIO

from threadsdelete.api import (
    SUPPORTED_CATEGORIES,
    UNSUPPORTED_CATEGORIES,
    ApiError,
    AuthError,
    Identity,
    ItemError,
    OwnershipError,
    QuotaExceededError,
    ThreadsClient,
    UnknownOutcomeError,
)
from threadsdelete.config import Config
from threadsdelete.core import (
    Candidate,
    Category,
    CategoryCounts,
    ExitCode,
    Operation,
    QuotaStatus,
    RunSummary,
    SelectionError,
    TimestampError,
    compute_cutoff,
    select_eligible,
)

SUMMARY_HEADER = "=== Summary ==="


class IdentityMismatchError(Exception):
    """The token belongs to a different account than THREADS_USER_ID."""


@dataclass
class Discovery:
    candidates: list[Candidate] = field(default_factory=list)
    scanned: dict[Category, int] = field(default_factory=dict)
    complete: bool = True
    problem: str | None = None


def verify_identity(client: ThreadsClient, expected_user_id: str) -> Identity:
    identity = client.get_identity()
    if identity.user_id != expected_user_id:
        raise IdentityMismatchError("the token's account does not match THREADS_USER_ID")
    return identity


def discover_all(client: ThreadsClient, identity: Identity) -> Discovery:
    """Finish discovery of every supported category; stop at the first non-auth failure."""
    result = Discovery(scanned={category: 0 for category in SUPPORTED_CATEGORIES})
    for category in SUPPORTED_CATEGORIES:
        try:
            found, scanned = client.discover(category, identity)
        except AuthError:
            raise
        except (ApiError, TimestampError, OwnershipError) as exc:
            result.complete = False
            result.problem = str(exc) or type(exc).__name__
            return result
        result.candidates.extend(found)
        result.scanned[category] = scanned
    return result


def split_by_budget(
    eligible: list[Candidate], cap: int, remaining: Mapping[Operation, int | None]
) -> tuple[list[Candidate], list[Candidate]]:
    """Walk the sorted list; allow while under the cap and the operation's quota."""
    allowed: list[Candidate] = []
    deferred: list[Candidate] = []
    used: dict[Operation, int] = {}
    for candidate in eligible:
        operation = candidate.operation
        quota = remaining.get(operation)
        within_quota = quota is None or used.get(operation, 0) < quota
        if len(allowed) < cap and within_quota:
            allowed.append(candidate)
            used[operation] = used.get(operation, 0) + 1
        else:
            deferred.append(candidate)
    return allowed, deferred


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _candidate_line(label: str, candidate: Candidate) -> str:
    return f"{label}  {candidate.category}  {candidate.target_id}  {candidate.permalink or '-'}"


def _summary_lines(summary: RunSummary) -> list[str]:
    lines = [SUMMARY_HEADER]
    for category, c in summary.counts.items():
        lines.append(
            f"{category}: scanned={c.scanned} eligible={c.eligible} "
            f"would_remove={c.would_remove} removed={c.removed} failed={c.failed} "
            f"unknown_outcome={c.unknown_outcome} deferred={c.deferred}"
        )
    return lines


def _check_quota(
    client: ThreadsClient, identity: Identity, summary: RunSummary
) -> tuple[Mapping[Operation, int | None], str]:
    """Quota inspection; any failure except auth falls back to the per-run cap."""
    try:
        quota = client.get_quota(identity)
    except AuthError:
        raise
    except ApiError:
        quota = None
    if quota is None:
        summary.quota_status = QuotaStatus.UNAVAILABLE
        return {}, (
            "Quota: unavailable \u2014 proceeding within MAX_DELETIONS_PER_RUN; "
            "the API's quota error stops removal"
        )
    summary.quota_status = QuotaStatus.AVAILABLE
    remaining: dict[Operation, int | None] = dict(quota.remaining)
    detail = ", ".join(f"{op}: {n} remaining" for op, n in quota.remaining.items())
    return remaining, f"Quota: available ({detail}, {quota.window_description})"


def _remove_all(
    client: ThreadsClient, allowed: list[Candidate], summary: RunSummary, out: TextIO
) -> tuple[list[Candidate], AuthError | None]:
    """Sequential removal. Returns candidates left unattempted and any auth failure."""
    for index, candidate in enumerate(allowed):
        counts = summary.counts[candidate.category]
        left = allowed[index + 1 :]
        try:
            client.remove(candidate)
        except ItemError as exc:
            counts.failed += 1
            print(_candidate_line("failed", candidate) + f"  ({exc})", file=out)
        except QuotaExceededError as exc:
            summary.notes.append(f"stopped: quota or rate limit reached ({exc})")
            return allowed[index:], None
        except UnknownOutcomeError as exc:
            counts.unknown_outcome += 1
            print(_candidate_line("unknown", candidate) + f"  ({exc})", file=out)
            summary.notes.append("stopped after unknown outcome; will rediscover next run")
            return left, None
        except AuthError as exc:
            summary.auth_failed = True
            summary.notes.append("stopped: authentication or permission failure")
            return allowed[index:], exc
        else:
            counts.removed += 1
            print(_candidate_line("removed", candidate), file=out)
    return [], None


def run(config: Config, client: ThreadsClient, run_started_at: datetime, out: TextIO) -> RunSummary:
    """Preview (dry run) or sequential removal. Raises AuthError / IdentityMismatchError."""
    identity = verify_identity(client, config.user_id)
    cutoff = compute_cutoff(run_started_at, config.days_ago)
    print(f"Account: @{identity.username} ({identity.user_id})", file=out)
    print(f"Cutoff (UTC): {_stamp(cutoff)}", file=out)
    mode = "DRY RUN (no changes will be made)" if config.dry_run else "REMOVAL"
    print(f"Mode: {mode}", file=out)
    for category, reason in UNSUPPORTED_CATEGORIES.items():
        print(f"Excluded: {category} \u2014 {reason}", file=out)

    summary = RunSummary(counts={c: CategoryCounts() for c in SUPPORTED_CATEGORIES})
    discovery = discover_all(client, identity)
    for category, scanned in discovery.scanned.items():
        summary.counts[category].scanned = scanned

    eligible: list[Candidate] = []
    problem = discovery.problem
    if discovery.complete:
        try:
            eligible = select_eligible(discovery.candidates, cutoff)
        except SelectionError as exc:
            discovery.complete = False
            problem = str(exc)
    summary.discovery_complete = discovery.complete

    quota_line = "Quota: not checked"
    remaining: Mapping[Operation, int | None] = {}
    if eligible:
        remaining, quota_line = _check_quota(client, identity, summary)

    allowed, deferred = split_by_budget(eligible, config.max_deletions_per_run, remaining)
    for candidate in eligible:
        summary.counts[candidate.category].eligible += 1
    for candidate in allowed:
        summary.counts[candidate.category].would_remove += 1

    auth_error: AuthError | None = None
    if config.dry_run:
        for candidate in allowed:
            print(_candidate_line("would remove", candidate), file=out)
    else:
        unattempted, auth_error = _remove_all(client, allowed, summary, out)
        deferred = unattempted + deferred
    for candidate in deferred:
        summary.counts[candidate.category].deferred += 1
        print(_candidate_line("deferred", candidate), file=out)

    for line in _summary_lines(summary):
        print(line, file=out)
    if summary.discovery_complete:
        print("Discovery: complete", file=out)
    else:
        print(f"Discovery: INCOMPLETE \u2014 {problem} (no changes made)", file=out)
    print(quota_line, file=out)
    for note in summary.notes:
        print(f"Note: {note}", file=out)
    if auth_error is not None:
        raise auth_error
    return summary


def exit_status(summary: RunSummary) -> ExitCode:
    """AUTH on auth loss; FAILURE on incomplete discovery or failed/unknown removals."""
    if summary.auth_failed:
        return ExitCode.AUTH
    if not summary.discovery_complete:
        return ExitCode.FAILURE
    if any(c.failed > 0 or c.unknown_outcome > 0 for c in summary.counts.values()):
        return ExitCode.FAILURE
    return ExitCode.OK
