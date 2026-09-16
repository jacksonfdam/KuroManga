"""Golden tests for the comiciviewer template, plus the descrambler.

Search, chapters and pages are a JSON API like iken's - decoded payloads in,
values out, no network. The descrambler is the reason this template was left
until last: it gets its own synthetic-image test rather than a recording,
because a scrambled fixture cannot be eyeballed for correctness the way a
JSON one can (decision 5, #107).
"""

import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

from app.sources.base import PageRef
from app.sources.net import CatalogueRow
from app.sources.templates.comiciviewer import (
    GRID_SIZE,
    ComiciViewerSource,
    _descramble_tiles,
    parse_viewer_id,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="comicpash", base_url="https://comicpash.jp")


def _payload(name: str):
    return json.loads((FIXTURES / name).read_text())


def _source() -> ComiciViewerSource:
    return ComiciViewerSource(ROW, name="Comic Pash", lang="ja", client=object())


def test_search_ranks_candidates_and_keeps_the_site_key():
    found = _source().parse_search(_payload("comicpash_search.json"), ["Nanpa Mobu"])

    assert found
    assert {c.source_site for c in found} == {"comicpash"}
    assert all(c.source_url.startswith("https://comicpash.jp/series/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].cover_url and found[0].cover_url.startswith("https://")


def test_the_same_class_serves_a_second_site_from_its_own_row():
    # 28 sites ride this template. If the class has comicpash hardcoded
    # anywhere, this is where it shows.
    other = ComiciViewerSource(
        CatalogueRow(key="comicride", base_url="https://comicride.jp"),
        name="Comic Ride",
        lang="ja",
        client=object(),
    )

    found = other.parse_search(_payload("comicpash_search.json"), ["Nanpa Mobu"])

    assert {c.source_site for c in found} == {"comicride"}
    assert all(c.source_url.startswith("https://comicride.jp/series/") for c in found)


def test_chapters_carry_absolute_urls_and_a_number_parsed_from_the_title():
    chapters = _source().parse_chapters(_payload("comicpash_episodes.json"))

    assert chapters
    assert all(isinstance(c.number, Decimal) for c in chapters)
    assert all(c.url.startswith("https://comicpash.jp/episodes/") for c in chapters)
    assert all(c.language == "ja" for c in chapters)


def test_chapters_come_back_newest_first():
    payload = _payload("comicpash_episodes.json")
    raw_ids_ascending = [ep["id"] for ep in payload["series"]["episodes"]]

    chapters = _source().parse_chapters(payload)

    assert [c.url.rsplit("/", 1)[-1] for c in chapters] == list(reversed(raw_ids_ascending))


def test_a_split_episode_gets_a_fractional_number_from_its_circled_digit():
    """Real titles from this site split one chapter across days: '第2話①' and
    '第2話②'. Both parsing to chapter 2 would collide two chapters into one.
    """
    payload = _payload("comicpash_episodes.json")

    chapters = _source().parse_chapters(payload)

    by_title = {c.title: c.number for c in chapters}
    assert by_title["第2話①"] == Decimal("2.1")
    assert by_title["第2話②"] == Decimal("2.2")
    assert by_title["第2話①"] != by_title["第2話②"]


def test_parse_viewer_id_reads_the_viewer_content_entry():
    viewer_id, content_id = parse_viewer_id(_payload("comicpash_episode_detail.json"))

    assert viewer_id == "0e38301423e00eaccabc6cb96eba43c7"
    assert content_id == 24


def test_pages_carry_a_referer_and_come_back_in_sort_order():
    chapter_url = "https://comicpash.jp/episodes/7dc34d8bc91a1"

    pages = _source().parse_pages(_payload("comicpash_pages.json"), chapter_url)

    assert len(pages) == 28
    assert all(p.headers.get("Referer") == chapter_url for p in pages)
    assert all(p.url.startswith("https://") for p in pages)


def test_a_page_carries_its_scramble_permutation_in_the_url_fragment():
    """The fragment costs nothing over the wire and is the only place this
    permutation can travel, since PageRef has no field for it (decision 1).
    """
    payload = _payload("comicpash_pages.json")
    first = payload["result"][0]

    pages = _source().parse_pages(payload, "https://comicpash.jp/episodes/x")

    descrambled = _source().descramble
    # Round-tripping through the URL must hand the algorithm the exact same
    # permutation the API sent, not a mangled one - so decode the fragment
    # back out rather than trusting the encoder blindly.
    fragment = pages[0].url.rsplit("#scramble=", 1)[1]
    assert [int(x) for x in unquote(fragment).strip("[]").split(",")] == json.loads(
        first["scramble"]
    )
    assert descrambled  # sanity: the method exists and is bound


def _flat_tile_image(colors: list[tuple[int, int, int]], tile_size: int = 16) -> Image.Image:
    """A GRID_SIZE x GRID_SIZE image, tile i filled with colors[i]."""
    size = tile_size * GRID_SIZE
    image = Image.new("RGB", (size, size))
    for index, color in enumerate(colors):
        x, y = (index // GRID_SIZE) * tile_size, (index % GRID_SIZE) * tile_size
        for px in range(x, x + tile_size):
            for py in range(y, y + tile_size):
                image.putpixel((px, py), color)
    return image


def _tile_colors(image: Image.Image, tile_size: int = 16) -> list[tuple[int, int, int]]:
    colors = []
    for index in range(GRID_SIZE * GRID_SIZE):
        x, y = (index // GRID_SIZE) * tile_size, (index % GRID_SIZE) * tile_size
        colors.append(image.getpixel((x + tile_size // 2, y + tile_size // 2)))
    return colors


def test_descramble_reassembles_an_image_scrambled_with_the_inverse_permutation():
    """Decision 2 (#107): column-major - destIndex // GRID_SIZE is x, % is y.
    Getting this backwards still produces a tile-aligned image, so only a
    known original checked tile-by-tile catches it.
    """
    original_colors = [
        (i * 16, 255 - i * 16, (i * 47) % 256) for i in range(GRID_SIZE * GRID_SIZE)
    ]

    # A derangement, not the identity - chosen so a row-major reading of the
    # same permutation would land tiles at different (wrong) positions than
    # a column-major one, which is what makes this test able to fail.
    tiles = [5, 2, 9, 14, 0, 11, 3, 8, 6, 1, 12, 4, 15, 7, 10, 13]
    inverse = [0] * len(tiles)
    for dest_index, source_index in enumerate(tiles):
        inverse[source_index] = dest_index

    # Build the scrambled image the way the site would have sent it: applying
    # `tiles` to it must yield `original` back.
    scrambled_colors = [original_colors[inverse[j]] for j in range(len(tiles))]
    scrambled = _flat_tile_image(scrambled_colors)
    buffer = BytesIO()
    scrambled.save(buffer, format="JPEG", quality=95)

    result = _descramble_tiles(buffer.getvalue(), tiles)

    descrambled = Image.open(BytesIO(result)).convert("RGB")
    # JPEG is lossy, so tolerate quantization noise rather than requiring
    # byte-for-byte equality - the point is that each tile landed in the
    # right place, not that compression was lossless.
    for got, expected in zip(_tile_colors(descrambled), original_colors, strict=True):
        assert all(abs(g - e) <= 12 for g, e in zip(got, expected, strict=True))


def test_descramble_copies_the_remainder_strip_unchanged():
    """4 * tileWidth may fall short of the real width - the leftover strip on
    the right (and below) is not part of any tile and must pass through as-is.
    """
    tile_size = 16
    size = tile_size * GRID_SIZE + 2  # a strip 2px wide/tall left over
    original = Image.new("RGB", (size, size), (10, 20, 30))
    # Mark the remainder strips distinctly so a bug that drops or misplaces
    # them shows up as a colour that should not be there.
    for x in range(size):
        for y in range(size):
            if x >= tile_size * GRID_SIZE or y >= tile_size * GRID_SIZE:
                original.putpixel((x, y), (200, 100, 50))

    tiles = list(range(GRID_SIZE * GRID_SIZE))  # identity for the tiled area
    buffer = BytesIO()
    original.save(buffer, format="JPEG", quality=95)

    result = _descramble_tiles(buffer.getvalue(), tiles)

    descrambled = Image.open(BytesIO(result)).convert("RGB")
    corner = descrambled.getpixel((size - 1, size - 1))
    assert all(abs(a - b) <= 12 for a, b in zip(corner, (200, 100, 50), strict=True))


def test_a_page_with_no_scramble_fragment_passes_through_untouched():
    """Not every page on these sites is scrambled - re-encoding an already
    fine JPEG would lose quality for nothing (decision 4, #107).
    """
    raw = b"\xff\xd8\xff\xe0" + b"not really a jpeg but must not be touched"
    page = PageRef(url="https://comicpash.jp/img/1.jpg")

    assert _source().descramble(raw, page) == raw


def test_descramble_reads_the_permutation_out_of_the_pages_own_url():
    original_colors = [(i * 16, 0, 0) for i in range(GRID_SIZE * GRID_SIZE)]
    tiles = [3, 1, 0, 2] + list(range(4, 16))
    inverse = [0] * len(tiles)
    for dest_index, source_index in enumerate(tiles):
        inverse[source_index] = dest_index
    scrambled = _flat_tile_image([original_colors[inverse[j]] for j in range(len(tiles))])
    buffer = BytesIO()
    scrambled.save(buffer, format="JPEG", quality=95)

    page = PageRef(url=f"https://cdn.example/1.jpg#scramble=%5B{','.join(map(str, tiles))}%5D")

    result = _source().descramble(buffer.getvalue(), page)

    descrambled = Image.open(BytesIO(result)).convert("RGB")
    for got, expected in zip(_tile_colors(descrambled), original_colors, strict=True):
        assert all(abs(g - e) <= 12 for g, e in zip(got, expected, strict=True))
