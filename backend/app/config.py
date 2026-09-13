from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "manga"
    postgres_password: str = "manga"
    postgres_db: str = "manga"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    library_path: Path = Path("/manga")
    download_concurrency: int = 3

    komga_url: str = "http://komga:25600"
    komga_api_key: str = ""
    komga_user: str = ""
    komga_pass: str = ""
    komga_library_name: str = "Manga"

    mal_client_id: str = ""
    mal_client_secret: str = ""
    anilist_client_id: str = ""
    anilist_client_secret: str = ""

    public_base_url: str = "http://localhost:8080"

    # MangaDex personal client. Optional: search and chapter feeds work anonymously,
    # and MangaDex caches anonymous responses but not authenticated ones.
    mangadex_client_id: str = ""
    mangadex_client_secret: str = ""
    mangadex_username: str = ""
    mangadex_password: str = ""

    downloader_binary: str = "manga-downloader"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def dsn(self) -> str:
        """Plain libpq DSN, for asyncpg connections that bypass SQLAlchemy."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
