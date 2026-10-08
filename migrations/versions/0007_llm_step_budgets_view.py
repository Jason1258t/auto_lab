"""llm_step_budgets view

A report for admins (drafts/token_budgets.md, phase 1, item 4): how each
pipeline step uses its token limit on each model. Written by hand:
autogenerate does not see views.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 11:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = """
CREATE VIEW llm_step_budgets AS
SELECT
    m.id                                   AS model_id,
    m.name                                 AS model_name,
    p.name                                 AS pipeline_name,
    pv.version_name,
    c.step_index,
    s.review_id IS NOT NULL                AS revise_step,
    count(*)                               AS calls,
    count(*) FILTER (WHERE c.status = 'failed') AS failed_calls,
    round(avg((c.params ->> 'max_tokens')::integer)) AS avg_limit,
    round(avg(r.input_tokens))             AS avg_input_tokens,
    round(avg(r.output_tokens))            AS avg_output_tokens,
    max(r.output_tokens)                   AS max_output_tokens,
    -- Shares are 0..1 over the calls with a response.
    round(avg((r.finish_reason = 'length')::integer), 3) AS cut_share,
    round(avg((NOT r.valid_json)::integer), 3)           AS invalid_share,
    round(avg(extract(epoch FROM c.finished_at - c.started_at)), 1) AS avg_seconds,
    -- Output tokens per second of the whole call (prompt reading included).
    round(sum(r.output_tokens)
          / nullif(sum(extract(epoch FROM c.finished_at - c.started_at))
                   FILTER (WHERE r.output_tokens IS NOT NULL), 0), 1) AS output_per_second
FROM llm_calls c
JOIN models m             ON m.id = c.model_id
JOIN tasks t              ON t.id = c.task_id
JOIN pipeline_versions pv ON pv.id = t.pipeline_version_id
JOIN pipelines p          ON p.id = pv.pipeline_id
JOIN task_steps s         ON s.task_id = c.task_id AND s.step_index = c.step_index
LEFT JOIN llm_responses r ON r.call_id = c.id
WHERE c.status IN ('done', 'failed')
GROUP BY m.id, m.name, p.name, pv.version_name, c.step_index, s.review_id IS NOT NULL
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(VIEW)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW llm_step_budgets")
