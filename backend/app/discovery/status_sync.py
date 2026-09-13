"""One internal status, four dialects.

Keeping the translation in one pure module is what makes "the same status
everywhere" checkable in a test rather than asserted in a comment.
"""

from app.enums import ListStatus

MAL = {
    ListStatus.READING: "reading",
    ListStatus.PLAN_TO_READ: "plan_to_read",
    ListStatus.COMPLETED: "completed",
    ListStatus.ON_HOLD: "on_hold",
    ListStatus.DROPPED: "dropped",
}

ANILIST = {
    ListStatus.READING: "CURRENT",
    ListStatus.PLAN_TO_READ: "PLANNING",
    ListStatus.COMPLETED: "COMPLETED",
    ListStatus.ON_HOLD: "PAUSED",
    ListStatus.DROPPED: "DROPPED",
}

# MangaDex happens to use the same words as MyAnimeList, but they are separate
# contracts: one of them changing must not silently change the other.
MANGADEX = {
    ListStatus.READING: "reading",
    ListStatus.PLAN_TO_READ: "plan_to_read",
    ListStatus.COMPLETED: "completed",
    ListStatus.ON_HOLD: "on_hold",
    ListStatus.DROPPED: "dropped",
}


def mal_status(status: ListStatus) -> str:
    return MAL[status]


def anilist_status(status: ListStatus) -> str:
    return ANILIST[status]


def mangadex_status(status: ListStatus) -> str:
    return MANGADEX[status]
