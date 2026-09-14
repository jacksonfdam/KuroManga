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


class SuggestionState(StrEnum):
    NEW = "new"
    DISMISSED = "dismissed"
    ADDED = "added"
