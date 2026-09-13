"""The forward-only guard.

This is the one place a bug writes wrong data to somebody else's service, where
it cannot be rolled back by fixing our database.
"""

from app.handlers.progress_write import forward_only


def test_forward_only_allows_a_higher_chapter():
    assert forward_only(current=10, requested=11) == 11


def test_forward_only_rejects_a_lower_chapter():
    assert forward_only(current=10, requested=4) is None


def test_forward_only_rejects_an_equal_chapter():
    assert forward_only(current=10, requested=10) is None
