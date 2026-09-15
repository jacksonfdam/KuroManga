"""Batch chunking.

Batching survives the binary, but its reason changed with it. It existed
because the downloader re-read a manga's whole chapter index on every
invocation, which made one job per chapter expensive. Under the Python path a
chapter costs one request, so a batch now exists to size the lease and to
amortise the series metadata read - and a single job for a whole backlog would
hold one lease for hours and fail all or nothing.

The range-spec and produced-file matching this file used to cover went with the
binary: nothing builds a command line for it to parse, and nothing reconciles
files it named.
"""

from app.handlers.batching import chunk


def test_batches_are_bounded_so_one_job_is_not_held_for_hours():
    assert chunk(list(range(1, 8)), 3) == [[1, 2, 3], [4, 5, 6], [7]]


def test_a_batch_size_below_one_still_makes_progress():
    assert chunk([1, 2], 0) == [[1], [2]]


def test_nothing_to_batch_produces_no_jobs():
    assert chunk([], 10) == []
