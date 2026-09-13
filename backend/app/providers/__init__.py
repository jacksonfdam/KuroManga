from app.enums import Provider
from app.providers.anilist import AniListSource
from app.providers.base import AnimeEntryDTO, ListEntryDTO, ListSource, RelatedManga, TokenSet
from app.providers.mal import MyAnimeListSource

__all__ = ["AnimeEntryDTO", "ListEntryDTO", "ListSource", "RelatedManga", "TokenSet", "get_source"]


def get_source(provider: Provider) -> ListSource:
    match provider:
        case Provider.MAL:
            return MyAnimeListSource()
        case Provider.ANILIST:
            return AniListSource()
    raise ValueError(f"unknown provider: {provider}")
