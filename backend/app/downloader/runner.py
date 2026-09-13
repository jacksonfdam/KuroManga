"""Invoke the manga-downloader binary and turn its output into progress.

The binary is a command line program, not a library, and its output format is
not a stable contract. Parsing lives here alone, covered by fixtures, so a change
upstream is a local fix.
"""

import asyncio
import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.config import get_settings
from app.downloader.paths import format_number

PERCENT = re.compile(r"(\d{1,3})\s*%")
FRACTION = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
MAX_ERROR_LINES = 15

ProgressCallback = Callable[[str, float | None], Awaitable[None]]


class DownloadError(RuntimeError):
    """The binary failed. Retryable unless the source says the chapter is absent."""


class ChapterUnavailable(DownloadError):
    """The chapter does not exist at the source, so retrying cannot help."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    stdout: str


@dataclass(frozen=True)
class BatchResult:
    paths: list[Path]
    stdout: str


def parse_progress(line: str) -> float | None:
    """Percentage from a progress line, or None when the line carries none."""
    match = PERCENT.search(line)
    if match:
        return min(float(match.group(1)), 100.0)
    fraction = FRACTION.search(line)
    if fraction:
        done, total = int(fraction.group(1)), int(fraction.group(2))
        if total > 0:
            return min(100.0 * done / total, 100.0)
    return None


def looks_unavailable(output: str) -> bool:
    lowered = output.casefold()
    return any(
        phrase in lowered
        for phrase in ("no chapters found", "chapter not found", "not available", "404")
    )


def build_command(
    source_url: str, chapter_range: str, output_dir: Path, *, language: str = "en"
) -> list[str]:
    """`manga-downloader [flags] [url] [ranges]`.

    The range is the whole point of batching: the tool fetches the chapter index
    once per invocation, so asking for twenty chapters costs one index fetch
    rather than twenty.
    """
    settings = get_settings()
    return [
        settings.downloader_binary,
        "--language",
        language,
        "--format",
        "cbz",
        "--output-dir",
        str(output_dir),
        source_url,
        chapter_range,
    ]


async def download_range(
    source_url: str,
    chapter_range: str,
    work_dir: Path,
    *,
    language: str = "en",
    on_progress: ProgressCallback | None = None,
) -> BatchResult:
    """Run the binary in an empty directory and return the archives it produced.

    The binary prompts for confirmation when a range is ambiguous, so stdin is
    closed: a prompt then fails immediately instead of hanging until the lease
    expires.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    for leftover in work_dir.iterdir():
        shutil.rmtree(leftover) if leftover.is_dir() else leftover.unlink()

    command = build_command(source_url, chapter_range, work_dir, language=language)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=work_dir,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    collected: list[str] = []
    assert process.stdout is not None
    async for raw in process.stdout:
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue
        collected.append(line)
        if on_progress is not None:
            await on_progress(line, parse_progress(line))

    code = await process.wait()
    output = "\n".join(collected)

    produced = sorted(work_dir.rglob("*.cbz"))

    if code != 0 and not produced:
        tail = "\n".join(collected[-MAX_ERROR_LINES:])
        if looks_unavailable(output):
            raise ChapterUnavailable(f"{chapter_range} unavailable at source: {tail}")
        raise DownloadError(f"downloader exited {code}: {tail}")

    if not produced:
        if looks_unavailable(output):
            raise ChapterUnavailable(f"{chapter_range} unavailable at source")
        raise DownloadError(f"downloader produced no cbz file: {output[-2000:]}")

    return BatchResult(paths=produced, stdout=output)


async def download_chapter(
    source_url: str,
    number: Decimal,
    work_dir: Path,
    *,
    language: str = "en",
    on_progress: ProgressCallback | None = None,
) -> DownloadResult:
    """One chapter, for manual retries. Batching is what the pipeline uses."""
    chapter_range = format_number(number).lstrip("0") or "0"
    batch = await download_range(
        source_url, chapter_range, work_dir, language=language, on_progress=on_progress
    )
    return DownloadResult(path=batch.paths[0], stdout=batch.stdout)
