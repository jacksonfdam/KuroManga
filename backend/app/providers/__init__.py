from app.enums import Provider
from app.providers.anilist import AniListSource
from app.providers.base import AnimeEntryDTO, ListEntryDTO, ListSource, RelatedManga, TokenSet
from app.providers.mal import MyAnimeListSource
from app.providers.mangabaka import MangaBakaSource

__all__ = [
    "AnimeEntryDTO",
    "ListEntryDTO",
    "ListSource",
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
    raise ValueError(f"unknown provider: {provider}")
