#!/usr/bin/env python3
"""Parses yuzono/tachiyomi-extensions into backend/app/catalogue/data/site_catalogue.json.

It parses. It does not transpile. Each extension is two machine-readable files:
a `build.gradle.kts` declaring name/lang/baseUrl/contentWarning/theme/versionCode,
and a leaf Kotlin class whose `override val`s and rate limit describe the one thing
a generated Python template does not already know about the site.

Everything is read with anchored regular expressions over the two files, never a
Kotlin grammar (issue #100, decision 2). A construct those patterns cannot read
confidently - an `override fun` doing real work, or an `override val` whose
right-hand side is not a literal - is not a parse failure. It is a site recorded as
`hand_ported = false`, shipped in the catalogue disabled, with the reason attached,
because the settings screen showing "disabled" with no explanation is the thing
this design keeps promising not to do.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The six templates this project ports first (design doc, "What the extension
# repository actually is"). A theme outside this set cannot be hand-ported yet
# for a reason no amount of regex sophistication fixes: nothing in this repo
# reads it, so every leaf on it is `hand_ported = false` regardless of what its
# own overrides look like.
SUPPORTED_TEMPLATES = frozenset(
    {"madara", "mangathemesia", "madaralegacy", "zeistmanga", "comiciviewer", "keyoapp"}
)

# SAFE is the only value that is not a content warning of its own.
_NSFW_WARNINGS = frozenset({"MIXED", "NSFW"})

_DURATION_UNIT_SECONDS = {"seconds": 1.0, "minutes": 60.0, "milliseconds": 0.001}


@dataclass(frozen=True)
class CatalogueEntry:
    """Mirrors app.catalogue.repo.CatalogueEntry field-for-field.

    Kept as a separate copy rather than an import: this tool runs against a
    scratch clone of an external repository with no app/ on its path, and the
    JSON it writes is the only contract with the loader - duplicating the shape
    here costs six field names, importing app.catalogue.repo would cost this
    script depending on the whole application package.
    """

    key: str
    name: str
    template: str
    base_url: str
    lang: str
    nsfw: bool
    overrides: dict[str, Any]
    rate_limit: dict[str, Any] | None
    version: str
    hand_ported: bool

    def as_dict(self) -> dict[str, Any]:
        # Field order here is the JSON's field order - part of the determinism
        # contract in decision 1, since dict insertion order is what json.dump
        # actually serialises.
        return {
            "key": self.key,
            "name": self.name,
            "template": self.template,
            "base_url": self.base_url,
            "lang": self.lang,
            "nsfw": self.nsfw,
            "overrides": self.overrides,
            "rate_limit": self.rate_limit,
            "version": self.version,
            "hand_ported": self.hand_ported,
        }


@dataclass
class GradleSource:
    lang: str
    base_url: str
    name: str


@dataclass
class GradleInfo:
    name: str
    version_code: str
    nsfw: bool
    theme: str | None
    sources: list[GradleSource]


@dataclass
class LeafInfo:
    overrides: dict[str, Any] = field(default_factory=dict)
    rate_limit: dict[str, Any] | None = None
    hand_ported: bool = True
    reason: str | None = None


def _match_brace(text: str, open_index: int) -> int | None:
    """Returns the index of the `}` matching the `{` at `open_index`, depth-counted.

    A non-greedy `\\{(.*?)\\}` regex is the obvious alternative and is wrong here:
    `baseUrl { custom("...") }` nests a brace pair inside a `source { }` block, so
    the first `}` a lazy regex finds belongs to the inner block, not the outer one.
    Counting depth is still a mechanical scan, not a grammar - it never learns what
    the braces mean, only how many are still open.
    """
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _extract_blocks(text: str, keyword: str) -> tuple[list[str], str]:
    """Finds every top-level `keyword { ... }` block, brace-matched.

    Returns the block bodies and `text` with each block blanked out, so a
    top-level field regex (`name = "..."`) run on the remainder cannot mistake a
    field declared inside one of those blocks for the top-level one.
    """
    blocks: list[str] = []
    out = []
    pos = 0
    pattern = re.compile(rf"(?<!\w){re.escape(keyword)}\s*\{{")
    while True:
        match = pattern.search(text, pos)
        if match is None:
            out.append(text[pos:])
            break
        open_index = match.end() - 1
        close_index = _match_brace(text, open_index)
        out.append(text[pos : match.start()])
        if close_index is None:
            # Unbalanced input - stop trusting this file rather than guess.
            out.append(text[match.start() :])
            pos = len(text)
            break
        blocks.append(text[open_index + 1 : close_index])
        pos = close_index + 1
    return blocks, "".join(out)


_STRING_LITERAL = re.compile(r'^"([^"$\\]*)"$')
_NUMBER_LITERAL = re.compile(r"^(-?\d+(?:\.\d+)?)[fFLl]?$")


_BASE_URL_LITERAL = re.compile(r'\bbaseUrl\s*=\s*"([^"$]*)"')
_BASE_URL_CUSTOM_BLOCK = re.compile(r'\bbaseUrl\s*\{\s*custom\(\s*"([^"$]*)"\s*\)\s*\}')
# `baseUrl { mirrors("a", "b", ...) }` declares fallback domains for one site.
# The first is the one worth calling "the" base URL - a later task can grow a
# real notion of mirrors; this tool only has to pick a value that resolves.
_BASE_URL_MIRRORS_BLOCK = re.compile(r'\bbaseUrl\s*\{\s*mirrors\(\s*"([^"$]*)"')
_LANG_LITERAL = re.compile(r'\blang\s*=\s*"([^"$]*)"')
_NAME_LITERAL = re.compile(r'\bname\s*=\s*"([^"$]*)"')

# `listOf("en", "ko", "all").forEach { source { lang = it; baseUrl = "..." } }`
# (or `.forEach { code -> source { lang = code; ... } }`) declares the same
# baseUrl under a fixed, literal list of languages. The list is literal even
# though the source block that consumes it is templated, so this is still an
# anchored pattern reading a constant - not a guess at what the loop produces.
_FOREACH_SOURCE_HEAD = re.compile(
    r'listOf\(\s*((?:"[^"]*"\s*,\s*)*"[^"]*"\s*,?\s*)\)\s*\.\s*forEach\s*\{\s*(?:(\w+)\s*->\s*)?'
)


def _base_url_from_block(block: str) -> str | None:
    literal = _BASE_URL_LITERAL.search(block)
    if literal:
        return literal.group(1)
    custom = _BASE_URL_CUSTOM_BLOCK.search(block)
    if custom:
        return custom.group(1)
    mirrors = _BASE_URL_MIRRORS_BLOCK.search(block)
    return mirrors.group(1) if mirrors else None


def _extract_foreach_sources(body: str) -> tuple[list[GradleSource], str]:
    """Splits out every `listOf(...).forEach { source { ... } }` construct.

    Returns the sources it could synthesise (name left `None` when the inner
    block never overrides it - the caller fills that in once it knows the
    top-level name) and `body` with each whole construct blanked, so the
    ordinary `source { }` scan run afterwards does not also trip over the
    templated block inside it and record it as an unparseable one for nothing.
    """
    sources: list[GradleSource] = []
    out = []
    pos = 0
    while True:
        head = _FOREACH_SOURCE_HEAD.search(body, pos)
        if head is None:
            out.append(body[pos:])
            break
        out.append(body[pos : head.start()])
        open_index = head.start() + head.group(0).rindex("{")
        close_index = _match_brace(body, open_index)
        if close_index is None:
            out.append(body[head.start() : head.end()])
            pos = head.end()
            continue

        lambda_body = body[open_index + 1 : close_index]
        inner_blocks, _ = _extract_blocks(lambda_body, "source")
        if len(inner_blocks) == 1:
            inner = inner_blocks[0]
            loop_var = head.group(2) or "it"
            base_url = _base_url_from_block(inner)
            has_loop_lang = re.search(rf"\blang\s*=\s*{re.escape(loop_var)}\b", inner)
            if base_url is not None and has_loop_lang:
                own_name_match = _NAME_LITERAL.search(inner)
                own_name = own_name_match.group(1) if own_name_match else None
                for lang_match in re.finditer(r'"([^"]*)"', head.group(1)):
                    sources.append(GradleSource(lang=lang_match.group(1), base_url=base_url, name=own_name))

        pos = close_index + 1

    return sources, "".join(out)


def parse_gradle(text: str) -> GradleInfo | None:
    """Reads the `keiyoushi { }` block's scalar fields and every `source { }` in it.

    Anything this cannot find with confidence (no name, no versionCode, no
    parseable source) is a `None`: the caller has nothing to build a row from,
    so there is no row rather than a guessed one.
    """
    keiyoushi_blocks, _ = _extract_blocks(text, "keiyoushi")
    if not keiyoushi_blocks:
        return None
    body = keiyoushi_blocks[0]

    foreach_sources, body = _extract_foreach_sources(body)
    source_blocks, outer = _extract_blocks(body, "source")

    name_match = re.search(r'(?m)^\s*name\s*=\s*"([^"$]*)"', outer)
    version_match = re.search(r"versionCode\s*=\s*(\d+)", outer)
    warning_match = re.search(r"contentWarning\s*=\s*ContentWarning\.(SAFE|MIXED|NSFW)", outer)
    theme_match = re.search(r'theme\s*=\s*"([^"$]*)"', outer)

    if name_match is None or version_match is None:
        return None

    top_name = name_match.group(1)
    nsfw = bool(warning_match) and warning_match.group(1) in _NSFW_WARNINGS
    theme = theme_match.group(1) if theme_match else None

    sources: list[GradleSource] = []
    for block in source_blocks:
        lang_match = _LANG_LITERAL.search(block)
        base_url = _base_url_from_block(block)
        if lang_match is None or base_url is None:
            # `lang = it` (a generated loop) or a `baseUrl` this tool's two known
            # forms - literal string, `custom(...)` block - both fail to match.
            continue
        own_name_match = _NAME_LITERAL.search(block)
        sources.append(
            GradleSource(
                lang=lang_match.group(1),
                base_url=base_url,
                name=own_name_match.group(1) if own_name_match else top_name,
            )
        )
    for source in foreach_sources:
        sources.append(GradleSource(lang=source.lang, base_url=source.base_url, name=source.name or top_name))

    return GradleInfo(
        name=top_name,
        version_code=version_match.group(1),
        nsfw=nsfw,
        theme=theme,
        sources=sources,
    )


def find_leaf_file(ext_dir: Path) -> Path | None:
    """The one `.kt` file declaring the `@Source`-annotated leaf class.

    An extension directory can carry helper files alongside it (an interceptor,
    a JSON model) - those never carry `@Source`, so filtering on the annotation
    is what tells the leaf apart from its own helpers rather than picking
    whichever `.kt` file sorts first.
    """
    candidates = sorted(ext_dir.glob("src/**/*.kt"))
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if "@Source" in text and re.search(r"class\s+\w+\s*:\s*\w+\(", text):
            return candidate
    return None


_RATE_LIMIT_DURATION = re.compile(
    r"rateLimit\(\s*(?:permits\s*=\s*)?(\d+)"
    r"(?:\s*,\s*(?:period\s*=\s*)?(\d+(?:\.\d+)?)\.(seconds|minutes|milliseconds))?"
)
_RATE_LIMIT_TIME_UNIT = re.compile(
    r"rateLimit\(\s*(\d+)\s*,\s*(\d+)\s*,\s*TimeUnit\.(SECONDS|MINUTES)\s*\)"
)


def _parse_rate_limit(text: str) -> dict[str, Any] | None:
    """Extracts the first `rateLimit(...)` call in the file, whichever form it uses.

    Handles both the Duration form this fork's `keiyoushi.network.rateLimit` takes
    (`rateLimit(3, 5.seconds)`, permits-only `rateLimit(3)`) and the older
    `rateLimit(3, 5, TimeUnit.SECONDS)` form some upstream history still carries -
    decision in the brief is explicit that both must be handled.

    This runs over the whole leaf file, independent of which function the call
    sits in and independent of `hand_ported` - a site the rest of this module
    refuses for an unrelated override still deserves the rate limit it declared,
    because net.py enforces it for every catalogue row, disabled or not, the
    moment a human re-enables the site.
    """
    match = _RATE_LIMIT_TIME_UNIT.search(text)
    if match:
        permits, amount, unit = match.groups()
        seconds = float(amount) * (60.0 if unit == "MINUTES" else 1.0)
        return {"permits": int(permits), "period_seconds": seconds}

    match = _RATE_LIMIT_DURATION.search(text)
    if match:
        permits, amount, unit = match.groups()
        if amount is None:
            seconds = 1.0  # keiyoushi.network.rateLimit's own default period.
        else:
            seconds = float(amount) * _DURATION_UNIT_SECONDS[unit]
        return {"permits": int(permits), "period_seconds": seconds}

    return None


def _configure_client_is_rate_limit_only(class_body: str) -> bool:
    """True when `configureClient` exists and does nothing but call `rateLimit`.

    That function is how every one of these sites declares a rate limit - Kotlin
    has no other place to hang it - so treating its presence alone as a
    disqualifying `override fun` would make the "extract rateLimit into
    rate_limit" rule in the brief nearly unreachable for any site that declares
    one. A `configureClient` that also adds an interceptor or otherwise touches
    the request (ddtteam's does) is real behaviour and still disqualifies; this
    function returns False for it same as for any other override fun.
    """
    sig = re.search(
        r"override\s+fun\s+OkHttpClient\.Builder\.configureClient\s*\([^)]*\)"
        r"(?:\s*:\s*OkHttpClient\.Builder)?\s*=?\s*",
        class_body,
    )
    if sig is None:
        return False  # no configureClient at all - nothing to exempt

    rest = class_body[sig.end() :]
    stripped = rest.lstrip()
    if stripped.startswith("{"):
        close = _match_brace(stripped, 0)
        content = stripped[1:close] if close is not None else stripped
    else:
        newline = rest.find("\n")
        content = rest[: newline if newline != -1 else len(rest)]

    content = content.strip()
    apply_match = re.match(r"^apply\s*\{(.*)\}$", content, re.DOTALL)
    if apply_match:
        content = apply_match.group(1).strip()

    only_call = re.match(
        r"^(?:this\.)?rateLimit\([^()]*(?:\([^()]*\)[^()]*)*\)"
        r"(?:\s*\{[^{}]*\})?$",
        content,
    )
    return bool(only_call)


def _find_class_body(text: str) -> str | None:
    """The leaf class's own body, or `""` for a bare `class X : Template()` with none."""
    match = re.search(r"class\s+\w+\s*:\s*\w+\([^)]*\)\s*", text)
    if match is None:
        return None
    rest = text[match.end() :]
    if not rest.lstrip().startswith("{"):
        return ""  # e.g. `abstract class WalpurgisScan : MangaThemesia()` - no overrides at all
    open_index = match.end() + (len(rest) - len(rest.lstrip()))
    close_index = _match_brace(text, open_index)
    if close_index is None:
        return None
    return text[open_index + 1 : close_index]


_OVERRIDE_FUN = re.compile(r"override\s+fun\s+(?:[\w.]+\.)?(\w+)\s*\(")
_OVERRIDE_VAL = re.compile(r"override\s+val\s+(\w+)\s*(?::\s*[\w<>?.]+)?\s*=\s*(.+)")


def parse_leaf(text: str) -> LeafInfo:
    info = LeafInfo()
    info.rate_limit = _parse_rate_limit(text)

    class_body = _find_class_body(text)
    if class_body is None:
        info.hand_ported = False
        info.reason = "leaf class body could not be located"
        return info
    if class_body == "":
        return info  # no overrides of any kind - trivially hand-ported

    fun_names = [m.group(1) for m in _OVERRIDE_FUN.finditer(class_body)]
    disqualifying_funs = [n for n in fun_names if n != "configureClient"]
    if "configureClient" in fun_names and not _configure_client_is_rate_limit_only(class_body):
        disqualifying_funs.append("configureClient")

    if disqualifying_funs:
        info.hand_ported = False
        info.reason = f"override fun {disqualifying_funs[0]} present"
        # Still record whatever literal vals sit alongside it - useful the day a
        # template absorbs this behaviour and the site becomes derivable.

    for line in class_body.splitlines():
        match = _OVERRIDE_VAL.match(line.strip())
        if match is None:
            continue
        prop_name, rhs = match.group(1), match.group(2).strip()
        literal, ok = _read_literal(rhs)
        if ok:
            info.overrides[prop_name] = literal
        elif info.hand_ported:
            info.hand_ported = False
            info.reason = f"override val {prop_name} is not a literal"

    return info


def _read_literal(rhs: str) -> tuple[Any, bool]:
    rhs = rhs.rstrip()
    # A trailing line comment on the same statement - "// wp-content etc" - is
    # common enough upstream that refusing every such line would refuse literals
    # for no reason; strip it before classifying.
    rhs = re.sub(r"\s*//.*$", "", rhs).strip()

    string_match = _STRING_LITERAL.match(rhs)
    if string_match:
        return string_match.group(1), True

    number_match = _NUMBER_LITERAL.match(rhs)
    if number_match:
        raw = number_match.group(1)
        return (float(raw) if "." in raw else int(raw)), True

    if rhs == "true":
        return True, True
    if rhs == "false":
        return False, True
    if rhs == "null":
        return None, True

    return None, False


def build_entries(
    repo_root: Path, templates: frozenset[str] | None = None
) -> tuple[list[CatalogueEntry], dict[str, Any]]:
    """Walks `src/<lang>/<name>/`, parsing what each extension declares.

    `templates`, when given, restricts the whole run to those themes - an
    extension on any other theme gets no row at all, not a disabled one. That is
    what lets a committed catalogue cover only the templates this project has
    actually ported without also committing a `hand_ported = false` row for
    every one of the other roughly 900 extensions upstream carries, which is
    what decision 5 in the brief asks this tool to avoid. Omit it to catalogue
    everything the repository has, `template_not_ported` and all - that is the
    shape a later template port expects to find waiting for it.

    Returns the entries and a stats dict this tool's own report is built from,
    so the measurement in the brief and the JSON it writes come from one pass,
    not two that could disagree.
    """
    entries: list[CatalogueEntry] = []
    stats: dict[str, Any] = {
        "extensions_seen": 0,
        "gradle_unparseable": 0,
        "by_template": {},
    }

    gradle_paths = sorted(repo_root.glob("src/*/*/build.gradle.kts"))
    for gradle_path in gradle_paths:
        stats["extensions_seen"] += 1
        ext_dir = gradle_path.parent
        dir_name = ext_dir.name

        gradle = parse_gradle(gradle_path.read_text(encoding="utf-8", errors="replace"))
        if gradle is None or not gradle.sources:
            stats["gradle_unparseable"] += 1
            continue

        theme = gradle.theme
        if templates is not None and theme not in templates:
            continue  # out of scope entirely - no row, not even a disabled one

        ported = theme in SUPPORTED_TEMPLATES
        if ported:
            leaf_path = find_leaf_file(ext_dir)
            leaf = (
                parse_leaf(leaf_path.read_text(encoding="utf-8", errors="replace"))
                if leaf_path is not None
                else LeafInfo(hand_ported=False, reason="leaf file not found")
            )
        else:
            reason = (
                f"theme '{theme}' has not been ported yet"
                if theme is not None
                else "extension declares no theme (standalone, not template-based)"
            )
            leaf = LeafInfo(hand_ported=False, reason=reason)

        # "Sites" here is one count per extension (per leaf Kotlin class), matching
        # how the design doc's own 478-site figure was measured - a multi-language
        # extension is one site with several catalogue rows sharing one
        # `hand_ported` verdict, not several sites, even though each language
        # variant still needs its own row for the source layer to reach it.
        template_label = theme or "none"
        bucket = stats["by_template"].setdefault(
            template_label, {"sites": 0, "sites_hand_ported": 0, "rows": 0}
        )
        bucket["sites"] += 1
        if leaf.hand_ported:
            bucket["sites_hand_ported"] += 1

        for source in gradle.sources:
            key = f"{source.lang}.{dir_name}"
            overrides = dict(leaf.overrides)
            if not leaf.hand_ported and leaf.reason:
                overrides["_reason"] = leaf.reason

            entries.append(
                CatalogueEntry(
                    key=key,
                    name=source.name,
                    template=theme or "none",
                    base_url=source.base_url,
                    lang=source.lang,
                    nsfw=gradle.nsfw,
                    overrides=overrides,
                    rate_limit=leaf.rate_limit,
                    version=gradle.version_code,
                    hand_ported=leaf.hand_ported,
                )
            )
            bucket["rows"] += 1

    entries.sort(key=lambda e: e.key)
    _check_unique_keys(entries)
    return entries, stats


def _check_unique_keys(entries: list[CatalogueEntry]) -> None:
    seen: set[str] = set()
    for entry in entries:
        if entry.key in seen:
            print(f"warning: duplicate catalogue key {entry.key!r}", file=sys.stderr)
        seen.add(entry.key)


def write_catalogue(entries: list[CatalogueEntry], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.as_dict() for entry in entries]
    # Two-space indent and a trailing newline, written once: decision 1's
    # determinism promise is only as good as this being the only place that
    # serialises - a second writer with different json.dump kwargs would pass
    # every test and still fail CI's byte-for-byte diff (#101).
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")


def _default_out_path() -> Path:
    return Path(__file__).resolve().parent.parent / "app" / "catalogue" / "data" / "site_catalogue.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="root of a yuzono/tachiyomi-extensions checkout (the directory containing src/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_default_out_path(),
        help="path to write the catalogue JSON to",
    )
    parser.add_argument(
        "--templates",
        type=str,
        default=None,
        help="comma-separated theme allowlist (default: every theme found)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print extension/hand_ported counts to stderr after writing",
    )
    args = parser.parse_args(argv)

    templates = frozenset(args.templates.split(",")) if args.templates else None
    entries, stats = build_entries(args.repo, templates)
    write_catalogue(entries, args.out)

    if args.report:
        print(f"extensions seen: {stats['extensions_seen']}", file=sys.stderr)
        print(f"gradle unparseable: {stats['gradle_unparseable']}", file=sys.stderr)
        for template, bucket in sorted(stats["by_template"].items()):
            print(
                f"  {template}: {bucket['sites_hand_ported']}/{bucket['sites']} sites hand_ported"
                f" ({bucket['rows']} catalogue rows)",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
