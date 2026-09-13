from enum import StrEnum


class Provider(StrEnum):
    MAL = "mal"
    ANILIST = "anilist"


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
    KOMGA_SCAN = "komga_scan"
    PROGRESS_PUSH = "progress_push"
