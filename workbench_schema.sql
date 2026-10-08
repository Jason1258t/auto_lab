-- AutoLab database schema (PostgreSQL 14+).
-- Snapshot for the course and the ER diagram. The source of truth for the
-- DDL is the Alembic migrations (migrations/versions/). This file matches
-- migrations 0001-0008 (checked with a pg_dump diff on 2026-10-08). After
-- each new migration, update it and check it the same way.
-- Design notes and reasons: drafts/schema_design.md and drafts/.
--
-- Rules used everywhere:
-- - Tables are snake_case and plural. Own key = id, links = <entity>_id.
-- - ENUM types for short fixed lists (statuses, kinds). text + CHECK
--   for lists that will grow with code soon (adapters, activity
--   actions). Lookup tables for values an admin may add.
-- - Deleting a person never deletes work: links to users are SET NULL.

BEGIN;

-- =====================================================================
-- Types (fixed lists)
-- =====================================================================

CREATE TYPE workspace_visibility AS ENUM ('private', 'public');
CREATE TYPE capability_kind      AS ENUM ('strength', 'weakness');
CREATE TYPE task_status          AS ENUM ('draft', 'queued', 'running',
                                          'in_review', 'done', 'cancelled',
                                          'failed');
CREATE TYPE task_step_status     AS ENUM ('pending', 'running', 'done');
CREATE TYPE llm_call_status      AS ENUM ('queued', 'running', 'done',
                                          'failed', 'cancelled');
CREATE TYPE finish_reason        AS ENUM ('stop', 'length', 'other');
CREATE TYPE source_kind          AS ENUM ('web', 'file');
CREATE TYPE review_result        AS ENUM ('accepted', 'rejected');
-- How big a step a model handles; *_think = a thinking model (0008).
CREATE TYPE model_size_class     AS ENUM ('small', 'medium', 'large',
                                          'small_think', 'medium_think', 'large_think');

-- =====================================================================
-- Group 1: People and access
-- =====================================================================

CREATE TABLE users (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email          text        NOT NULL,
    username       text        NOT NULL UNIQUE,
    display_name   text        NOT NULL,
    email_verified boolean     NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Emails are compared without case.
CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));

CREATE TABLE workspaces (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text        NOT NULL,
    description text,
    -- Creator never changes. Owner can change; NULL = free project
    -- (public + archived) or the owner's account was deleted.
    created_by  bigint      REFERENCES users (id) ON DELETE SET NULL,
    owner_id    bigint      REFERENCES users (id) ON DELETE SET NULL,
    visibility  workspace_visibility NOT NULL DEFAULT 'private',
    archived_at timestamptz,  -- NULL = active
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Public once, public forever. A CHECK cannot see the old value,
-- so a trigger does it.
CREATE FUNCTION workspaces_keep_public() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.visibility = 'public' AND NEW.visibility <> 'public' THEN
        RAISE EXCEPTION 'workspace % is public and cannot become private', OLD.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER workspaces_keep_public
    BEFORE UPDATE OF visibility ON workspaces
    FOR EACH ROW EXECUTE FUNCTION workspaces_keep_public();

CREATE TABLE roles (
    id          smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text     NOT NULL UNIQUE,
    description text
);

-- A person can have many roles in one workspace.
-- The owner is workspaces.owner_id, not a row here.
CREATE TABLE memberships (
    workspace_id bigint   NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id      bigint   NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id      smallint NOT NULL REFERENCES roles (id) ON DELETE RESTRICT,
    PRIMARY KEY (workspace_id, user_id, role_id)
);

-- User files of a workspace (added in migration 0003). A file is copied
-- into data/workspaces/<workspace_id>/files/<file_name>.
CREATE TABLE workspace_files (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workspace_id  bigint      NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    original_name text        NOT NULL,
    original_path text,       -- for people only, never used to open a file
    file_name     text        NOT NULL,  -- current name on disk: '<id>_<safe name>'
    size_bytes    bigint      NOT NULL CHECK (size_bytes >= 0),
    sha256        text        NOT NULL,
    content_type  text,
    uploaded_by   bigint      REFERENCES users (id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, file_name)
);

-- =====================================================================
-- Group 2: Model catalog
-- =====================================================================

-- An admin can add a provider without a migration, if its adapter
-- exists in code.
CREATE TABLE model_providers (
    id        smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      text     NOT NULL UNIQUE,
    adapter   text     NOT NULL
                       CHECK (adapter IN ('ollama', 'openai_compatible', 'anthropic')),
    base_url  text,
    secret_id text     -- key id in the external secret store, no FK
);

-- One model from one provider = one row. Models are never deleted,
-- only marked unavailable.
CREATE TABLE models (
    id                 bigint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id        smallint      NOT NULL REFERENCES model_providers (id) ON DELETE RESTRICT,
    name               text          NOT NULL,  -- name the provider API expects
    base_url           text,                    -- NULL = model_providers.base_url
    context_length     integer       NOT NULL CHECK (context_length > 0),
    vram_mb            integer       CHECK (vram_mb >= 0),  -- NULL for cloud
    ram_mb             integer       CHECK (ram_mb >= 0),   -- NULL for cloud
    cost_per_1m_input  numeric(10,4) CHECK (cost_per_1m_input >= 0),   -- NULL = free
    cost_per_1m_output numeric(10,4) CHECK (cost_per_1m_output >= 0),  -- NULL = free
    description        text,
    available          boolean       NOT NULL DEFAULT true,
    created_at         timestamptz   NOT NULL DEFAULT now(),
    -- Token budgets (drafts/token_budgets.md, migration 0008).
    size_class         model_size_class NOT NULL DEFAULT 'small',
    reasoning_tokens   integer       CHECK (reasoning_tokens > 0),   -- NULL = 1024; *_think only
    max_output_tokens  integer       CHECK (max_output_tokens > 0),  -- NULL = no own cap
    UNIQUE (provider_id, name)
);

CREATE TABLE capabilities (
    id          smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text     NOT NULL UNIQUE,
    description text
);

CREATE TABLE model_capabilities (
    model_id      bigint   NOT NULL REFERENCES models (id) ON DELETE CASCADE,
    capability_id smallint NOT NULL REFERENCES capabilities (id) ON DELETE RESTRICT,
    kind          capability_kind NOT NULL,
    note          text,
    PRIMARY KEY (model_id, capability_id)
);

-- =====================================================================
-- Group 3: Tasks
-- =====================================================================

-- A pipeline is the task type (research, study_notes, ...).
CREATE TABLE pipelines (
    id          smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text     NOT NULL UNIQUE,
    description text
);

-- One row = one fixed snapshot of a pipeline YAML file.
-- New tasks use the newest version (MAX version_code).
CREATE TABLE pipeline_versions (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id  smallint    NOT NULL REFERENCES pipelines (id) ON DELETE RESTRICT,
    version_name text        NOT NULL,  -- '1.0.1', for people
    version_code integer     NOT NULL CHECK (version_code > 0),  -- for sorting
    file_path    text        NOT NULL,
    file_hash    text        NOT NULL,  -- sha256; the file must never change
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, version_code),
    UNIQUE (pipeline_id, version_name)
);

CREATE TABLE tasks (
    id                  bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: only an empty workspace can be deleted.
    workspace_id        bigint      NOT NULL REFERENCES workspaces (id) ON DELETE RESTRICT,
    pipeline_version_id bigint      NOT NULL REFERENCES pipeline_versions (id) ON DELETE RESTRICT,
    model_id            bigint      NOT NULL REFERENCES models (id) ON DELETE RESTRICT,
    title               text        NOT NULL,
    input               text        NOT NULL,  -- the user's request
    -- 'done' <=> an accepted row in task_reviews (kept in sync by the backend).
    status              task_status NOT NULL DEFAULT 'draft',
    created_by          bigint      REFERENCES users (id) ON DELETE SET NULL,
    reviewer_id         bigint      REFERENCES users (id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    finished_at         timestamptz
);

-- Created before task_steps, because a revise step points to the review
-- that caused it.
CREATE TABLE task_reviews (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id     bigint      NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    reviewer_id bigint      REFERENCES users (id) ON DELETE SET NULL,
    result      review_result NOT NULL,
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- A rejection needs a comment: it is the input for the revise steps.
    CHECK (result = 'accepted' OR comment IS NOT NULL)
);

CREATE TABLE task_steps (
    task_id     bigint      NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    step_index  smallint    NOT NULL CHECK (step_index >= 0),
    -- A cancelled task puts its running step back to 'pending'.
    status      task_step_status NOT NULL DEFAULT 'pending',
    summary     text,       -- the model's short report about the step
    -- NULL = normal pipeline step; set = extra revise step caused by
    -- this review. RESTRICT: a review is deleted only with its task.
    review_id   bigint      REFERENCES task_reviews (id) ON DELETE RESTRICT,
    started_at  timestamptz,
    finished_at timestamptz,
    PRIMARY KEY (task_id, step_index)
);

-- One row = one request to a model. id is also the key in the log store,
-- where the full prompt and output live.
CREATE TABLE llm_calls (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id         bigint      NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    step_index      smallint    NOT NULL,
    model_id        bigint      NOT NULL REFERENCES models (id) ON DELETE RESTRICT,
    attempt         smallint    NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    -- 'done' <=> a row in llm_responses (kept in sync by the backend).
    status          llm_call_status NOT NULL DEFAULT 'queued',
    response_schema jsonb,      -- NULL = free text
    params          jsonb,      -- temperature, max_tokens, seed, ...
    error           text,       -- short message, safe to show to users
    created_at      timestamptz NOT NULL DEFAULT now(),  -- entered the queue
    started_at      timestamptz,
    finished_at     timestamptz,
    FOREIGN KEY (task_id, step_index)
        REFERENCES task_steps (task_id, step_index) ON DELETE CASCADE
);

-- 0 or 1 response per call. Cost is not stored: tokens x model price.
CREATE TABLE llm_responses (
    call_id       bigint      PRIMARY KEY REFERENCES llm_calls (id) ON DELETE CASCADE,
    input_tokens  integer     CHECK (input_tokens >= 0),
    output_tokens integer     CHECK (output_tokens >= 0),
    -- The adapter maps the provider's value; the raw value is in the log store.
    finish_reason finish_reason,
    valid_json    boolean,    -- NULL = no schema
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Outbox for the log cleanup worker. No FK: the call row is already gone.
CREATE TABLE log_deletions (
    call_id    bigint      PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Fires for direct deletes and for CASCADE from tasks.
CREATE FUNCTION llm_calls_queue_log_deletion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO log_deletions (call_id) VALUES (OLD.id)
    ON CONFLICT (call_id) DO NOTHING;
    RETURN OLD;
END;
$$;

CREATE TRIGGER llm_calls_queue_log_deletion
    BEFORE DELETE ON llm_calls
    FOR EACH ROW EXECUTE FUNCTION llm_calls_queue_log_deletion();

-- =====================================================================
-- Group 4: Results and evidence
-- =====================================================================

-- A task produces one work. Title = tasks.title.
CREATE TABLE works (
    task_id    bigint      PRIMARY KEY REFERENCES tasks (id) ON DELETE CASCADE,
    summary    text,
    file_path  text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- One source used in one work. The full text is not stored.
CREATE TABLE work_sources (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_id     bigint      NOT NULL REFERENCES works (task_id) ON DELETE CASCADE,
    title       text        NOT NULL,
    kind        source_kind NOT NULL,
    location    text        NOT NULL,  -- URL, or file name with part of its path
    accessed_at timestamptz NOT NULL,
    UNIQUE (work_id, location)
);

-- Claim and exact quote in one row. A claim with two sources = two rows.
CREATE TABLE quotes (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_source_id bigint      NOT NULL REFERENCES work_sources (id) ON DELETE CASCADE,
    claim          text        NOT NULL,
    quote          text        NOT NULL,
    placement      text,       -- URL with anchor, or 'p. 67, line 12'
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- A public signature for publications. Does not show the workspace.
CREATE TABLE publishers (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text        NOT NULL UNIQUE,
    description text,
    owner_id    bigint      REFERENCES users (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE publications (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: a published work protects its task.
    work_id      bigint      NOT NULL UNIQUE REFERENCES works (task_id) ON DELETE RESTRICT,
    publisher_id bigint      NOT NULL REFERENCES publishers (id) ON DELETE RESTRICT,
    title        text        NOT NULL,
    description  text,
    published_at timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- Group 5: Audit and logging
-- =====================================================================

-- Important human actions. No FKs: rows must survive deletes.
-- Names are copied, so the log still reads well later.
CREATE TABLE activity_events (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    actor_id     bigint,     -- NULL = the system
    actor_name   text,
    workspace_id bigint,     -- NULL = global action (admins only)
    action       text        NOT NULL
                             CHECK (action IN (
                                 'member_added', 'member_removed',
                                 'role_added', 'role_removed',
                                 'workspace_taken', 'made_public', 'archived',
                                 'task_deleted', 'work_published',
                                 'publisher_created',
                                 'admin_granted', 'admin_revoked',
                                 'user_deleted',
                                 'unarchived', 'workspace_deleted',
                                 'file_added', 'file_removed',
                                 'pipeline_uploaded')),
    target_type  text        CHECK (target_type IN (
                                 'workspace', 'membership', 'task', 'work',
                                 'publication', 'publisher', 'user', 'file',
                                 'pipeline')),
    target_id    bigint,
    target_label text,
    details      jsonb
);

-- =====================================================================
-- Group 6: Auth
-- =====================================================================

-- Login uses users.email.
CREATE TABLE password_credentials (
    user_id       bigint      PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    password_hash text        NOT NULL,  -- argon2, never the password
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- External login providers. Built later.
CREATE TABLE auth_providers (
    id      smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name    text     NOT NULL UNIQUE,
    enabled boolean  NOT NULL DEFAULT false
);

CREATE TABLE user_identities (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          bigint      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider_id      smallint    NOT NULL REFERENCES auth_providers (id) ON DELETE RESTRICT,
    provider_user_id text        NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_id, provider_user_id)
);

-- A row here = an admin.
CREATE TABLE admins (
    user_id    bigint      PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    granted_at timestamptz NOT NULL DEFAULT now(),
    granted_by text        -- plain text for now
);

-- Refresh tokens, stored only as a hash. Access tokens are short JWTs
-- and are not stored.
CREATE TABLE sessions (
    id                 bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            bigint      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    refresh_token_hash text        NOT NULL UNIQUE,
    created_at         timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    last_used_at       timestamptz,
    revoked_at         timestamptz,  -- NULL = active
    -- The token before the last refresh; it still works for a few
    -- seconds after rotated_at (a page reload during a refresh).
    previous_token_hash text,
    rotated_at         timestamptz,
    CHECK (expires_at > created_at),
    CONSTRAINT sessions_previous_token_check
        CHECK ((previous_token_hash IS NULL) = (rotated_at IS NULL))
);

-- =====================================================================
-- Indexes (PK and UNIQUE already have one)
-- =====================================================================

CREATE INDEX memberships_user_id_idx ON memberships (user_id);
CREATE INDEX workspaces_owner_id_idx ON workspaces (owner_id);
CREATE INDEX tasks_workspace_created_idx ON tasks (workspace_id, created_at DESC);
CREATE INDEX tasks_active_status_idx ON tasks (status)
    WHERE status IN ('queued', 'running');
CREATE INDEX tasks_in_review_reviewer_idx ON tasks (reviewer_id)
    WHERE status = 'in_review';
CREATE INDEX task_steps_review_id_idx ON task_steps (review_id);
CREATE INDEX llm_calls_task_step_idx ON llm_calls (task_id, step_index);
CREATE INDEX task_reviews_task_id_idx ON task_reviews (task_id);
CREATE INDEX quotes_work_source_id_idx ON quotes (work_source_id);
CREATE INDEX publications_publisher_published_idx
    ON publications (publisher_id, published_at DESC);
CREATE INDEX activity_events_workspace_occurred_idx
    ON activity_events (workspace_id, occurred_at DESC);
CREATE INDEX sessions_user_id_idx ON sessions (user_id);
CREATE INDEX user_identities_user_id_idx ON user_identities (user_id);

-- =====================================================================
-- Views (reports)
-- =====================================================================

-- Token budgets per model and pipeline step (drafts/token_budgets.md):
-- is the limit too small (cut_share), too big (avg/max output far below
-- avg_limit), and how fast is the model.
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
GROUP BY m.id, m.name, p.name, pv.version_name, c.step_index, s.review_id IS NOT NULL;

-- =====================================================================
-- Seed data
-- =====================================================================

INSERT INTO roles (name, description) VALUES
    ('editor',   'Can create and edit tasks'),
    ('reviewer', 'Can review results'),
    ('member',   'Is in the workspace; can read');

INSERT INTO model_providers (name, adapter, base_url) VALUES
    ('ollama', 'ollama', 'http://localhost:11434');

INSERT INTO capabilities (name, description) VALUES
    ('json_output', 'Returns valid JSON for a given schema'),
    ('summarize',   'Summarizes a text');

INSERT INTO pipelines (name, description) VALUES
    ('research',         'Any topic, with search and verification'),
    ('opinion_survey',   'What sources say about a topic'),
    ('study_notes',      'Notes on a topic, search is optional'),
    ('creative_writing', 'Creative text, no search, no verification'),
    -- migration 0005
    ('deep_research',    'Long research in rounds, many sources, every claim with a quote'),
    ('code',             'One small program, written and checked by static analysis'),
    ('python_cli',       'Python command-line tool, planned and checked step by step');

INSERT INTO auth_providers (name) VALUES
    ('github'),
    ('google');

COMMIT;
