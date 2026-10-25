import random
import unittest
from datetime import UTC, datetime, timedelta

from threadsdelete.core import (
    Candidate,
    Category,
    Operation,
    SelectionError,
    TimestampError,
    compute_cutoff,
    is_eligible,
    parse_timestamp,
    select_eligible,
)

RUN_START = datetime(2026, 10, 23, 5, 0, 0, tzinfo=UTC)


def cand(category: Category, target_id: str, action_at: datetime) -> Candidate:
    return Candidate(category, target_id, action_at, None)


class CutoffTests(unittest.TestCase):
    def test_cutoff_boundary_before_at_after(self) -> None:
        cutoff = compute_cutoff(RUN_START, 90)
        self.assertEqual(cutoff, RUN_START - timedelta(days=90))
        one = timedelta(seconds=1)
        self.assertTrue(is_eligible(cand(Category.POST, "1", cutoff - one), cutoff))
        self.assertTrue(is_eligible(cand(Category.POST, "2", cutoff), cutoff))
        self.assertFalse(is_eligible(cand(Category.POST, "3", cutoff + one), cutoff))

    def test_zero_days_includes_content_up_to_run_start(self) -> None:
        cutoff = compute_cutoff(RUN_START, 0)
        self.assertEqual(cutoff, RUN_START)
        before = cand(Category.POST, "1", RUN_START)
        after = cand(Category.POST, "2", RUN_START + timedelta(seconds=1))
        self.assertEqual(select_eligible([before, after], cutoff), [before])

    def test_naive_run_start_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compute_cutoff(datetime(2026, 10, 23, 5, 0, 0), 90)


class TimestampTests(unittest.TestCase):
    def test_offsets_are_normalised_to_utc(self) -> None:
        instant = datetime(2024, 1, 31, 12, 0, 0, tzinfo=UTC)
        for text in (
            "2024-01-31T12:00:00+0000",
            "2024-01-31T12:00:00Z",
            "2024-01-31T12:00:00+00:00",
            "2024-01-31T04:00:00-0800",
        ):
            parsed = parse_timestamp(text)
            self.assertEqual(parsed, instant, text)
            self.assertEqual(parsed.utcoffset(), timedelta(0), text)

    def test_malformed_and_naive_timestamps_rejected(self) -> None:
        for bad in ("2024-01-31T12:00:00", "2024-01-31", "garbage", "", None, 1706702400, b"x"):
            with self.assertRaises(TimestampError, msg=repr(bad)):
                parse_timestamp(bad)


class SelectionTests(unittest.TestCase):
    def test_reposts_use_the_delete_operation(self) -> None:
        self.assertIs(cand(Category.REPOST, "5", RUN_START).operation, Operation.DELETE)
        self.assertEqual({o.value for o in Operation}, {"delete", "unlike"})
        cutoff = compute_cutoff(RUN_START, 10)
        base = RUN_START - timedelta(days=30)
        with self.assertRaises(SelectionError):
            select_eligible(
                [
                    cand(Category.REPOST, "5", base),
                    cand(Category.POST, "5", base - timedelta(days=1)),
                ],
                cutoff,
            )

    def test_duplicates_collapse_and_order_is_deterministic(self) -> None:
        cutoff = compute_cutoff(RUN_START, 10)
        base = RUN_START - timedelta(days=30)
        items = [
            cand(Category.REPLY, "b", base),
            cand(Category.POST, "z", base),
            cand(Category.POST, "a", base),
            cand(Category.POST, "m", base - timedelta(days=1)),
            cand(Category.POST, "a", base),
            cand(Category.QUOTE, "q", base),
        ]
        expected = select_eligible(items, cutoff)
        self.assertEqual(
            [(c.category, c.target_id) for c in expected],
            [
                (Category.POST, "m"),
                (Category.POST, "a"),
                (Category.POST, "z"),
                (Category.QUOTE, "q"),
                (Category.REPLY, "b"),
            ],
        )
        rng = random.Random(7)
        for _ in range(5):
            shuffled = list(items)
            rng.shuffle(shuffled)
            self.assertEqual(select_eligible(shuffled, cutoff), expected)

    def test_conflicting_duplicate_timestamps_raise(self) -> None:
        cutoff = compute_cutoff(RUN_START, 10)
        base = RUN_START - timedelta(days=30)
        items = [cand(Category.POST, "a", base), cand(Category.POST, "a", base - timedelta(days=1))]
        with self.assertRaises(SelectionError):
            select_eligible(items, cutoff)


if __name__ == "__main__":
    unittest.main()
