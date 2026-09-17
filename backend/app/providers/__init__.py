from app.enums import Provider
from app.providers.anilist import AniListSource
from app.providers.base import AnimeEntryDTO, ListEntryDTO, ListSource, RelatedManga, TokenSet
from app.providers.local import LocalSource
from app.providers.mal import MyAnimeListSource
from app.providers.mangabaka import MangaBakaSource

__all__ = [
    "AnimeEntryDTO",
    "ListEntryDTO",
    "ListSource",
    "LocalSource",
    "MangaBakaSource",
    "RelatedManga",
    "TokenSet",
    "get_source",
]


def get_source(provider: Provider) -> ListSource:
    match provider:
        case Provider.MAL:
            return MyAnimeListSource()
        case Provider.ANILIST:
            return AniListSource()
        case Provider.MANGABAKA:
            return MangaBakaSource()
        case Provider.LOCAL:
            return LocalSource()
    raise ValueError(f"unknown provider: {provider}")


def syncing_providers() -> list[Provider]:
    """Providers with a remote list to pull, asked of the providers themselves.

    The cron, the manual refresh and the integrations panel all used to iterate
    the enum. A provider answering from this database would be scheduled hourly
    against a list that does not exist, and reported as an integration waiting
    for a sign-in it has no way to perform.
    """
    return [provider for provider in Provider if get_source(provider).syncs]
