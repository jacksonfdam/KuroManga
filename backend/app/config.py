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

    # Where app/mcp reaches the API. The MCP server runs beside a model rather
    # than inside Compose, so it addresses the published port instead of the
    # `api` service name.
    kuromanga_api_url: str = "http://localhost:8080"

    # MangaDex personal client. Optional: search and chapter feeds work anonymously,
    # and MangaDex caches anonymous responses but not authenticated ones.
    # MangaBaka API key. Full account access, so it stays in .env and is never
    # written to the database.
    mangabaka_token: str = ""

    mangadex_client_id: str = ""
    mangadex_client_secret: str = ""
    mangadex_username: str = ""
    mangadex_password: str = ""

    # Self-hosted comick-source-api. It scrapes search results and chapter
    # lists, but has no endpoint for page images, so it never touches
    # downloading itself.
    comick_api_url: str = "http://comick:3000"

    # Headless-Chrome Cloudflare challenge solver. Empty by default, and its
    # Compose service sits behind the `flaresolverr` profile (#92, decision
    # 6) - it is a several-hundred-megabyte image nobody sourcing from
    # MangaDex needs, and #115 is an open issue about exactly that pattern
    # being got wrong for another service.
    flaresolverr_url: str = ""

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
