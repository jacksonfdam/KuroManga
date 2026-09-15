"""tools/gen_catalogue.py against a checked-in slice of the real extension repository.

The slice under tests/data/extensions/ is five real extensions copied verbatim
from yuzono/tachiyomi-extensions (issue #100, decision 6): a single-source leaf
with several literal overrides and a rate limit, a multi-source gradle file, a
leaf with one literal val and one fun override, and one on a template this
project has not ported. Each file is what it claims to be - a reader can open
the original upstream path this tool preserved and see the same source.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
DATA_DIR = Path(__file__).parent / "data" / "extensions"


def _load_gen_catalogue():
    # tools/ is a standalone script directory, not part of the app package
    # setuptools installs - importing it like any other module keeps this test
    # from needing a second copy of the parser to exercise it against.
    spec = importlib.util.spec_from_file_location("gen_catalogue", TOOLS_DIR / "gen_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


g = _load_gen_catalogue()


def _entries_by_key():
    entries, _stats = g.build_entries(DATA_DIR)
    return {entry.key: entry for entry in entries}


def test_a_single_source_leaf_with_literal_overrides_is_hand_ported():
    entry = _entries_by_key()["en.mangatx"]
    assert entry.hand_ported is True
    assert entry.template == "mangathemesia"
    assert entry.base_url == "https://mangatx.cc"
    assert entry.overrides == {
        "mangaUrlDirectory": "/manga-list",
        "datePattern": "dd-MM-yyyy",
        "seriesAuthorSelector": ".imptdt:contains(Author) a",
        "supportsRelatedMangas": False,
    }
    assert entry.rate_limit == {"permits": 3, "period_seconds": 1.0}


def test_a_multi_source_gradle_file_yields_one_row_per_source():
    """seraphicdeviltry declares an en and an es `source { }` block sharing one leaf."""
    entries = _entries_by_key()
    en = entries["en.seraphicdeviltry"]
    es = entries["es.seraphicdeviltry"]

    assert en.base_url == "https://seraphic-deviltry.com"
    assert es.base_url == "https://spanish.seraphic-deviltry.com"
    # Both rows share the one leaf class, so both carry the same verdict and
    # the same rate limit - the override that disqualifies the site is not a
    # property of one language variant.
    assert en.hand_ported is False
    assert es.hand_ported is False
    assert en.overrides["_reason"] == es.overrides["_reason"]
    assert en.rate_limit == es.rate_limit == {"permits": 3, "period_seconds": 1.0}


def test_a_leaf_with_one_literal_val_and_one_fun_override_lands_disabled():
    """komikav overrides `hasProjectPage` (a literal) and `configureClient` (a real
    interceptor, not just a rate limit) - the fun override disqualifies it even
    though the val beside it would have been perfectly readable on its own.
    """
    entry = _entries_by_key()["id.komikav"]
    assert entry.hand_ported is False
    assert entry.overrides["_reason"] == "override fun configureClient present"
    # The literal val is still recorded - useful the day configureClient's
    # interceptor becomes something the template itself models.
    assert entry.overrides["hasProjectPage"] is True


def test_a_site_on_an_unported_template_is_disabled_with_that_reason():
    entry = _entries_by_key()["it.ddtteam"]
    assert entry.template == "pizzareader"
    assert entry.hand_ported is False
    assert "pizzareader" in entry.overrides["_reason"]
    assert "not been ported" in entry.overrides["_reason"]


def test_a_bare_leaf_with_no_overrides_is_trivially_hand_ported():
    entry = _entries_by_key()["it.walpurgisscan"]
    assert entry.hand_ported is True
    assert entry.overrides == {}
    assert entry.rate_limit is None


def test_every_row_deserialises_into_the_catalogue_entry_shape():
    entries, _stats = g.build_entries(DATA_DIR)
    for entry in entries:
        payload = entry.as_dict()
        assert list(payload.keys()) == [
            "key",
            "name",
            "template",
            "base_url",
            "lang",
            "nsfw",
            "overrides",
            "rate_limit",
            "version",
            "hand_ported",
        ]


def test_output_is_sorted_by_key():
    entries, _stats = g.build_entries(DATA_DIR)
    keys = [entry.key for entry in entries]
    assert keys == sorted(keys)


def test_running_the_generator_twice_produces_identical_bytes(tmp_path):
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    entries_a, _ = g.build_entries(DATA_DIR)
    g.write_catalogue(entries_a, out_a)
    entries_b, _ = g.build_entries(DATA_DIR)
    g.write_catalogue(entries_b, out_b)

    assert out_a.read_bytes() == out_b.read_bytes()


def test_written_json_round_trips_through_the_stdlib_parser():
    entries, _stats = g.build_entries(DATA_DIR)
    payload = [entry.as_dict() for entry in entries]
    assert json.loads(json.dumps(payload)) == payload


def test_cli_writes_to_the_given_path(tmp_path):
    out_path = tmp_path / "catalogue.json"
    exit_code = g.main(["--repo", str(DATA_DIR), "--out", str(out_path)])
    assert exit_code == 0
    written = json.loads(out_path.read_text())
    assert {row["key"] for row in written} == {
        "en.mangatx",
        "en.seraphicdeviltry",
        "es.seraphicdeviltry",
        "id.komikav",
        "it.ddtteam",
        "it.walpurgisscan",
    }


# The pin: which upstream revision the committed catalogue was generated from.
#
# Without it the CI guard cannot exist. Upstream merges every few hours, so a
# check that regenerates against a moving `main` and diffs the result would fail
# pull requests that touched neither the generator nor the catalogue - it would
# be reporting that upstream moved, which is the scheduled job's business, not
# the guard's.


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def _checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    (repo / "src" / "en" / "x").mkdir(parents=True)
    (repo / "src" / "en" / "x" / "build.gradle.kts").write_text("// placeholder\n")
    _git(repo.parent, "init", "-q", repo.name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def test_the_pin_records_the_revision_of_the_checkout_it_read(tmp_path):
    gen = _load_gen_catalogue()
    repo = _checkout(tmp_path)
    expected = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    written = gen.write_pin(repo, tmp_path / "upstream.txt")

    assert written == expected
    # Trailing newline, like the catalogue itself: a file without one is a diff
    # against every editor that adds it.
    assert (tmp_path / "upstream.txt").read_text() == f"{expected}\n"


def test_a_directory_that_is_not_a_checkout_pins_nothing(tmp_path):
    gen = _load_gen_catalogue()
    plain = tmp_path / "slice"
    plain.mkdir()

    written = gen.write_pin(plain, tmp_path / "upstream.txt")

    # The checked-in test slice is not a git repository, and a generator that
    # refused to run against it would make this suite impossible. Skipping the
    # pin is the honest answer: there is no revision to record.
    assert written is None
    assert not (tmp_path / "upstream.txt").exists()


def test_the_cli_writes_the_pin_beside_the_catalogue(tmp_path):
    gen = _load_gen_catalogue()
    repo = _checkout(tmp_path)
    out = tmp_path / "catalogue.json"
    pin = tmp_path / "upstream.txt"

    gen.main(["--repo", str(repo), "--out", str(out), "--pin", str(pin)])

    assert pin.read_text().strip()
    assert out.exists()
