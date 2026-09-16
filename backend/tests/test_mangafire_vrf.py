"""MangaFire's request signature.

These are guard tests, not proof of correctness. Only the site can say whether a
signature is right, and this project cannot reach it from the suite. What they
do is make the failure legible: if the constants are edited, if the canonical
form drifts, or if someone "tidies" the sort, a test goes red here rather than
every request quietly coming back unauthorised weeks later.

The golden values below were produced by this implementation. They are checked
in so that a change to it has to be deliberate — they say "this is what we send
today", which is exactly what you need when the site rotates its tables and you
are trying to work out whether the port or the site changed.
"""

import base64

import pytest

from app.sources.mangafire.vrf import _STAGES, canonical, sign


def test_the_three_stages_are_shaped_as_the_extension_declares_them():
    """Extracted from VrfSigner.kt rather than transcribed; this is the check that
    the extraction produced what the algorithm needs."""
    assert len(_STAGES) == 3
    assert [len(table) for table, _, _ in _STAGES] == [256, 256, 256]
    assert [iv for _, _, iv in _STAGES] == [0x5A, 0x35, 0xBA]
    assert all(key for _, key, _ in _STAGES)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/titles?keyword=naruto", "8sK3xtqdFZfetBhus6bRAjHyEL3W3A"),
        ("", ""),
    ],
)
def test_signing_is_stable(path, expected):
    assert sign(path) == expected


def test_the_signature_is_url_safe_and_unpadded():
    """It travels as a query parameter. `+` and `/` would be re-encoded by any
    client that touches the URL, and `=` padding is what the extension strips."""
    value = sign("/titles?page=1&limit=50")
    assert "=" not in value
    assert "+" not in value
    assert "/" not in value
    # Decodable as URL-safe base64 once the padding is put back.
    base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_a_different_path_signs_differently():
    assert sign("/titles?page=1") != sign("/titles?page=2")


def test_the_api_prefix_is_dropped():
    """`/api/titles` signs as `/titles`. Signing the sent path instead is the
    kind of mistake that looks right in the URL and is refused by the site."""
    assert canonical("/api/titles", []) == "/titles"


def test_parameters_are_sorted_by_name():
    assert canonical("/api/titles", [("page", "1"), ("keyword", "n"), ("limit", "50")]) == (
        "/titles?keyword=n&limit=50&page=1"
    )


def test_a_repeated_name_keeps_the_order_it_was_given():
    """Sorted by name only. Sorting by value too would reorder a filter list and
    change the signature without changing the request."""
    assert canonical("/api/titles", [("genres[]", "7"), ("genres[]", "5")]) == (
        "/titles?genres[0]=7&genres[1]=5"
    )


def test_a_bracketed_name_is_written_with_its_index():
    assert canonical("/api/titles", [("genres[]", "5"), ("genres[]", "7"), ("page", "1")]) == (
        "/titles?genres[0]=5&genres[1]=7&page=1"
    )


def test_the_index_restarts_for_each_name():
    assert canonical(
        "/api/titles",
        [("genres[]", "5"), ("genres[]", "7"), ("types[]", "manga")],
    ) == "/titles?genres[0]=5&genres[1]=7&types[0]=manga"


def test_a_path_with_no_parameters_has_no_question_mark():
    assert canonical("/api/titles/abc/chapters", []) == "/titles/abc/chapters"
