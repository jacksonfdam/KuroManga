from enum import StrEnum


class Provider(StrEnum):
    MAL = "mal"
    ANILIST = "anilist"
    MANGABAKA = "mangabaka"


class ListStatus(StrEnum):
    READING = "reading"
    PLAN_TO_READ = "plan_to_read"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    DROPPED = "dropped"


class ChapterState(StrEnum):
    KNOWN = "known"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DONE = "done"
    FAILED = "failed"


class JobType(StrEnum):
    LIST_SYNC = "list_sync"
    MATCH_SEARCH = "match_search"
    CHAPTER_DISCOVER = "chapter_discover"
    DOWNLOAD_CHAPTER = "download_chapter"
    DOWNLOAD_BATCH = "download_batch"
    KOMGA_SCAN = "komga_scan"
    PROGRESS_PUSH = "progress_push"
    PROGRESS_WRITE = "progress_write"
    ANIME_LIST_SYNC = "anime_list_sync"
    SUGGEST_BUILD = "suggest_build"
    LIST_WRITE = "list_write"
    MEDIA_ENRICH = "media_enrich"
    STATUS_WRITE = "status_write"
    NOTES_WRITE = "notes_write"


class Lane(StrEnum):
    """Which worker process may take a job.

    Downloads hold a slot for minutes at a time; everything else is short and is
    what a user is waiting on. Sharing one pool let a backlog of the first
    starve the second, and priority could not fix it: priority decides who
    enters a free slot, not who may keep one.
    """

    FETCH = "fetch"
    DOWNLOAD = "download"


# Stated as the download set rather than both, so a new job type joins the fetch
# lane by omission. That is the safe default: a short job in the download lane
# waits behind archives, while a long one in the fetch lane is merely the
# behaviour we already had.
_DOWNLOAD_LANE = frozenset({JobType.DOWNLOAD_BATCH, JobType.DOWNLOAD_CHAPTER})


def lane_of(job_type: JobType) -> Lane:
    return Lane.DOWNLOAD if job_type in _DOWNLOAD_LANE else Lane.FETCH


def types_for(lane: Lane) -> list[str]:
    """The job types a process in this lane may lease, as the query wants them."""
    return sorted(str(job_type) for job_type in JobType if lane_of(job_type) is lane)


class SuggestionState(StrEnum):
    NEW = "new"
    DISMISSED = "dismissed"
    ADDED = "added"


class ProgressSource(StrEnum):
    """Which path recorded a progress_event."""

    KOMGA = "komga"
    MANUAL = "manual"
