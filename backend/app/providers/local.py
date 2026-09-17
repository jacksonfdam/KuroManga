"""The list this installation keeps for itself.

Most of what a reader actually reads is not on MyAnimeList or AniList. A manhwa
picked up from a scanlation site the week it started has no entry to write to,
and the interface said so honestly and then stopped: the progress control
disabled itself and the one series the reader was actually reading was the one
they could not record.

So there is a fourth provider, and it is not a service. It holds a `list_entry`
row like any other, which is what lets every part of the pipeline that already
knows how to read progress keep working unchanged - the forward-only guard, the
chapter ceiling, the reading-frequency log, the library's progress column. What
it does not have is a remote list, which is why it syncs nothing and
authenticates with nothing.
"""

from app.enums import ListStatus, Provider
from app.providers.base import ListEntryDTO, ListSource


class LocalSource(ListSource):
    provider = Provider.LOCAL

    # Nowhere to sign in to, nothing to pull, nothing to search. The three
    # capability flags are what keep this provider out of the loops that would
    # otherwise ask it to behave like a service.
    uses_oauth = False
    syncs = False
    can_search = False

    #: The whole point. A local entry exists so that a series no remote list
    #: will accept still has somewhere for a chapter to land.
    writable = True

    @classmethod
    def static_credential(cls) -> str | None:
        """Always connected.

        `progress_write` refuses a series with no connected entry, and connected
        means a stored token or a configured key. There is no credential to
        configure here and the write never leaves this process, so the answer is
        a constant - the alternative is a token row for a provider that has no
        account behind it.
        """
        return "local"

    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        """Nothing to fetch: this list is already in the database it would write to."""
        return []

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        """No push. `progress_write` updates `list_entry` itself once this returns,
        and that row is the whole of this provider."""

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        """The same: the caller writes the row this provider is made of."""
