from app.text_utils import normalize, similarity, slugify


def test_normalize_folds_case_punctuation_and_spacing():
    assert normalize("Escape  Machine!") == normalize("escape machine")


def test_normalize_keeps_distinct_titles_distinct():
    assert normalize("Escape Machine") != normalize("Escape Mechanism")


def test_slugify_produces_a_filesystem_safe_name():
    assert slugify("Tousou Kikou: Ver. 2!") == "tousou-kikou-ver-2"


def test_slugify_never_returns_empty():
    assert slugify("???") == "untitled"


def test_similarity_ranks_the_closer_title_higher():
    assert similarity("Escape Machine", "Escape Machine") > similarity(
        "Escape Machine", "Something Else"
    )
