"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATEMENTS = [
    """CREATE TABLE provider_token (
	provider VARCHAR(20) NOT NULL, 
	access_token TEXT NOT NULL, 
	refresh_token TEXT, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	account_name VARCHAR(200), 
	PRIMARY KEY (provider)
)""",
    """CREATE TABLE series (
	id BIGSERIAL NOT NULL, 
	canonical_title VARCHAR(500) NOT NULL, 
	slug VARCHAR(300) NOT NULL, 
	komga_series_id VARCHAR(100), 
	needs_review BOOLEAN NOT NULL, 
	meta JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
)""",
    """CREATE TABLE setting (
	key VARCHAR(100) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY (key)
)""",
    """CREATE TABLE chapter (
	id BIGSERIAL NOT NULL, 
	series_id BIGINT NOT NULL, 
	number NUMERIC(8, 2) NOT NULL, 
	title VARCHAR(500), 
	source_url TEXT, 
	state VARCHAR(20) NOT NULL, 
	file_path TEXT, 
	komga_book_id VARCHAR(100), 
	discovered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_chapter_series_number UNIQUE (series_id, number), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE CASCADE
)""",
    """CREATE TABLE job (
	id BIGSERIAL NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	payload JSONB NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	priority INTEGER NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	lease_until TIMESTAMP WITH TIME ZONE, 
	run_after TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	last_error TEXT, 
	dedupe_key VARCHAR(200), 
	series_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_job_expiry ON job (state, lease_until)""",
    """CREATE INDEX ix_job_lease ON job (state, priority, created_at)""",
    """CREATE UNIQUE INDEX ix_job_dedupe ON job (type, dedupe_key) WHERE state in ('pending', 'leased') and dedupe_key is not null""",
    """CREATE TABLE list_entry (
	id BIGSERIAL NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	provider_media_id VARCHAR(50) NOT NULL, 
	series_id BIGINT, 
	title_romaji VARCHAR(500), 
	title_english VARCHAR(500), 
	synonyms JSONB NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	user_progress_chapter INTEGER NOT NULL, 
	total_chapters INTEGER, 
	cover_url TEXT, 
	raw JSONB NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_list_entry_provider_media UNIQUE (provider, provider_media_id), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE SET NULL
)""",
    """CREATE TABLE series_candidate (
	id BIGSERIAL NOT NULL, 
	series_id BIGINT NOT NULL, 
	source_site VARCHAR(50) NOT NULL, 
	source_url TEXT NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	cover_url TEXT, 
	chapter_count INTEGER, 
	year INTEGER, 
	score NUMERIC(5, 4) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE CASCADE
)""",
    """CREATE TABLE source_mapping (
	id BIGSERIAL NOT NULL, 
	series_id BIGINT NOT NULL, 
	source_site VARCHAR(50) NOT NULL, 
	source_url TEXT NOT NULL, 
	active BOOLEAN NOT NULL, 
	confirmed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE CASCADE
)""",
    """CREATE TABLE job_event (
	id BIGSERIAL NOT NULL, 
	job_id BIGINT NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	level VARCHAR(10) NOT NULL, 
	message TEXT NOT NULL, 
	pct NUMERIC(5, 2), 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES job (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_job_event_job_ts ON job_event (job_id, ts)""",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("drop table if exists job_event cascade")
    op.execute("drop table if exists source_mapping cascade")
    op.execute("drop table if exists series_candidate cascade")
    op.execute("drop table if exists list_entry cascade")
    op.execute("drop table if exists job cascade")
    op.execute("drop table if exists chapter cascade")
    op.execute("drop table if exists setting cascade")
    op.execute("drop table if exists series cascade")
    op.execute("drop table if exists provider_token cascade")
