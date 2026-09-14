"""series the user does not want Review to keep asking about

Revision ID: 0006_review_ignored
Revises: 0005_progress_event
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_review_ignored"
down_revision: str | None = "0005_progress_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A column rather than a deletion, because the series is not going anywhere:
    # it stays in the library, on its lists and in every sync. The only thing
    # this answers is "stop putting this one in front of me", and the answer has
    # to outlive the next list_sync — which upserts the series row and would
    # otherwise hand back a question the user already turned down.
    #
    # Deliberately not folded into needs_review: that flag is the pipeline's own
    # record of whether a mapping is missing, and match_search sets it back to
    # true on every search. A user's decision cannot live in a column a cron job
    # overwrites.
    op.execute("alter table series add column if not exists review_ignored_at timestamptz")


def downgrade() -> None:
    op.execute("alter table series drop column if exists review_ignored_at")
