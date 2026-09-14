from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import (
    ChapterState,
    JobState,
    JobType,
    ListStatus,
    ProgressSource,
    Provider,
    SuggestionState,
)


class Base(DeclarativeBase):
    pass


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Series(Base):
    """Canonical series. One per manga, shared by every list entry pointing at it."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    komga_series_id: Mapped[str | None] = mapped_column(String(100))
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Downloading is opt in. Discovery still runs, so the interface can show what
    # exists before anything is fetched.
    auto_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set when the user tells Review to stop asking about this series. Nothing
    # else reads it: the series keeps its list entries, its Komga folder and its
    # place in every sync, and an unmapped series was already downloading
    # nothing. Null is the normal state, so the review queue is the default.
    review_ignored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _now()

    entries: Mapped[list["ListEntry"]] = relationship(back_populates="series")
    mappings: Mapped[list["SourceMapping"]] = relationship(back_populates="series")
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="series")
    candidates: Mapped[list["SeriesCandidate"]] = relationship(back_populates="series")


class ListEntry(Base):
    """One entry as it exists on a remote list provider."""

    __tablename__ = "list_entry"
    __table_args__ = (
        UniqueConstraint("provider", "provider_media_id", name="uq_list_entry_provider_media"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[Provider] = mapped_column(String(20), nullable=False)
    provider_media_id: Mapped[str] = mapped_column(String(50), nullable=False)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))

    title_romaji: Mapped[str | None] = mapped_column(String(500))
    title_english: Mapped[str | None] = mapped_column(String(500))
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ListStatus] = mapped_column(String(20), nullable=False)
    user_progress_chapter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chapters: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    series: Mapped[Series | None] = relationship(back_populates="entries")


class SourceMapping(Base):
    """User-confirmed link between a canonical series and a source site URL."""

    __tablename__ = "source_mapping"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    source_site: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_at: Mapped[datetime] = _now()

    series: Mapped[Series] = relationship(back_populates="mappings")


class SeriesCandidate(Base):
    """Search result awaiting the user's confirmation on the review screen."""

    __tablename__ = "series_candidate"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    source_site: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    chapter_count: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)

    series: Mapped[Series] = relationship(back_populates="candidates")


class Chapter(Base):
    """What is known to exist, and what state the local copy is in."""

    __tablename__ = "chapter"
    __table_args__ = (
        UniqueConstraint("series_id", "number", name="uq_chapter_series_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)
    state: Mapped[ChapterState] = mapped_column(
        String(20), nullable=False, default=ChapterState.KNOWN
    )
    file_path: Mapped[str | None] = mapped_column(Text)
    komga_book_id: Mapped[str | None] = mapped_column(String(100))
    discovered_at: Mapped[datetime] = _now()

    series: Mapped[Series] = relationship(back_populates="chapters")


class Job(Base):
    """The queue. Leased with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        Index("ix_job_lease", "state", "priority", "created_at"),
        Index("ix_job_expiry", "state", "lease_until"),
        Index(
            "ix_job_dedupe",
            "type",
            "dedupe_key",
            unique=True,
            postgresql_where=text("state in ('pending', 'leased') and dedupe_key is not null"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[JobType] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[JobState] = mapped_column(String(20), nullable=False, default=JobState.PENDING)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_after: Mapped[datetime] = _now()
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    """Append-only progress log. Feeds the SSE stream and the log view."""

    __tablename__ = "job_event"
    __table_args__ = (Index("ix_job_event_job_ts", "job_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = _now()
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    pct: Mapped[float | None] = mapped_column(Numeric(5, 2))


class ProviderToken(Base):
    __tablename__ = "provider_token"

    provider: Mapped[Provider] = mapped_column(String(20), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_name: Mapped[str | None] = mapped_column(String(200))


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AnimeEntry(Base):
    """One anime as it exists on a remote list provider, relations included."""

    __tablename__ = "anime_entry"
    __table_args__ = (
        UniqueConstraint("provider", "provider_media_id", name="uq_anime_entry_provider_media"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[Provider] = mapped_column(String(20), nullable=False)
    provider_media_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title_romaji: Mapped[str | None] = mapped_column(String(500))
    title_english: Mapped[str | None] = mapped_column(String(500))
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ListStatus] = mapped_column(String(20), nullable=False)
    progress_episode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_episodes: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    related_manga: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    manga_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Suggestion(Base):
    """A manga worth reading because an anime on the list adapts it."""

    __tablename__ = "suggestion"
    __table_args__ = (
        UniqueConstraint("provider", "provider_media_id", name="uq_suggestion_provider_media"),
        # `desc` is not decoration: the Discovery list is ordered by rank_score
        # descending, and an index declared ascending here is a difference
        # alembic autogenerate would offer to "fix" against the migration.
        Index("ix_suggestion_state_rank", "state", desc("rank_score")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[Provider] = mapped_column(String(20), nullable=False)
    provider_media_id: Mapped[str] = mapped_column(String(50), nullable=False)
    alt_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    total_chapters: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    publishing_status: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[SuggestionState] = mapped_column(
        String(20), nullable=False, default=SuggestionState.NEW
    )
    rank_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProgressEvent(Base):
    """Append-only record of reading progress moving forward.

    `list_entry.user_progress_chapter` is overwritten by every sync, so it can
    say where reading stands and never when it got there. One row per forward
    movement of a series, written by the jobs that move it.
    """

    __tablename__ = "progress_event"
    __table_args__ = (Index("ix_progress_event_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    chapter: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # How many chapters this movement covers, so a jump from 3 to 10 counts as
    # seven chapters read rather than as one event.
    delta: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    source: Mapped[ProgressSource] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _now()
