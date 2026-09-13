from decimal import Decimal

from app.handlers.progress_push import highest_completed
from app.komga.client import parse_books


def _numbers(books):
    return {book.id: Decimal(str(index + 1)) for index, book in enumerate(books)}


def test_the_furthest_finished_chapter_wins(fixture):
    books = parse_books(fixture("komga_books.json"))
    assert highest_completed(books, _numbers(books)) == Decimal("1")


def test_unfinished_books_do_not_count(fixture):
    books = parse_books(fixture("komga_books.json"))
    numbers = _numbers(books)
    assert highest_completed(books, numbers) < numbers[books[1].id]


def test_books_the_pipeline_did_not_place_are_ignored(fixture):
    books = parse_books(fixture("komga_books.json"))
    assert highest_completed(books, {}) is None


def test_nothing_read_reports_none(fixture):
    books = [book for book in parse_books(fixture("komga_books.json")) if not book.completed]
    assert highest_completed(books, _numbers(books)) is None
