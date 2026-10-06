# Results and evidence (Group 4, done)

Working notes. Rewritten from the author's Russian draft (2026-09-26).
Items marked **(proposal)** are Claude's suggestions and are not decided
yet.

Last updated: 2026-09-28

## Idea

- **Works (materials).** A task produces one work: a file in a separate
  folder. Task and work are 1 : 1. Later a material can be more than one
  file (a folder of sorted files). Workspace model: `workspaces.md`.
- **Sources.** Full source text is not stored. A source is a title and a
  location (URL or workspace file).
- **Evidence.** Structure: `work → source → quote`, each arrow is
  one-to-many. Here a "source" means *the use of a source in one work*,
  not a global list of web pages.
- **Quote location.** Flexible: a link (URL with anchor) or plain text
  like "p. 67, line 12".
- **Task review ≠ publication review.** They are different entities.
  - *Task review*: the internal check by the assigned reviewer. Separate
    table, so later it can grow into reviews of single steps.
  - *Publication review* (a public critique): after MVP.
- **Publications.** A work can be published. A publication shows where
  it comes from, but it does not depend on workspace visibility. A
  **publisher** groups and signs publications without showing the
  workspace.
- **Work versions**: after MVP.

This replaces the old plan (`sources`, `claims`, `claim_evidence` as
separate tables): claim and quote now live in one row.

## Tables

### works
A separate table (not columns in `tasks`), because a task has no work
until it is finished. Same idea as `llm_responses`.

| Column | Type | Null | Notes |
|---|---|---|---|
| task_id | bigint | no | PK, → tasks, `CASCADE` (see open question 8) |
| summary | text | yes | short summary of the result |
| file_path | text | no | e.g. `data/works/2026/09/<task_id>.md` |
| created_at | timestamptz | no | default `now()` |
| updated_at | timestamptz | no | changes after a revision |

The title comes from `tasks.title`. Accepted = an `accepted` row exists
in `task_reviews` (decided 2026-09-28); no extra field.

### work_sources
One row = one source used in one work.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_id | bigint | no | → works, `CASCADE` |
| title | text | no | |
| kind | enum `source_kind` | no | `web` / `file` (decided 2026-09-26) |
| location | text | no | URL for `web`; file name with part of its path in the workspace for `file` |
| accessed_at | timestamptz | no | **(proposal)** when the page was read; pages change over time |

Unique: `(work_id, location)` **(proposal)**.

### quotes
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_source_id | bigint | no | → work_sources, `CASCADE` |
| claim | text | no | statement in the work |
| quote | text | no | **(proposal)** exact text from the source that supports the claim |
| placement | text | yes | where the quote is: URL with anchor, or "p. 67, line 12" |
| created_at | timestamptz | no | default `now()` |

### task_reviews
Internal review of a task's work. Named `task_reviews`, not `reviews`,
because publication reviews will be a different table later.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| task_id | bigint | no | → tasks, `CASCADE` |
| reviewer_id | bigint | yes | → users, `SET NULL` |
| result | enum `review_result` | no | `accepted` / `rejected` |
| comment | text | yes | required for `rejected`: `CHECK (result = 'accepted' OR comment IS NOT NULL)` |
| created_at | timestamptz | no | default `now()` |

### publishers
A public "signature" for publications. Hides the workspace.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| name | text | no | unique |
| description | text | yes | |
| owner_id | bigint | yes | → users, `SET NULL`; only the owner can publish under it (MVP, decided 2026-09-28) |
| created_at | timestamptz | no | default `now()` |

### publications
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_id | bigint | no | → works; unique (one publication per work); delete rule: open question 8 |
| publisher_id | bigint | no | → publishers, `RESTRICT` |
| title | text | no | public title, can differ from the task title |
| description | text | yes | |
| published_at | timestamptz | no | default `now()` |

## Revision after a rejected review (proposal)

The reviewer rejects the work and writes what to fix. Then:

1. The task goes back into the queue.
2. The orchestrator adds **extra steps** to the same task: new
   `task_steps` rows with the next `step_index`, of a built-in kind
   `revise`. This kind is not in the pipeline file.
3. The `revise` steps get the review comment as input, change the work
   file, and update `works.updated_at`.
4. The work waits for a new review.

Schema changes this needs:

- `task_steps.review_id` bigint, NULL, → task_reviews. NULL = a normal
  pipeline step; not NULL = extra step caused by this review.
- New task status `in_review` between `running` and `done`:

```
draft → queued → running → in_review → done
                    ↑           │
                    └─ rejected ┘  (task queued again, extra steps added)
```

Why not a new task per revision: task and work are 1 : 1, so the fix
must stay in the same task.

Known limit: the work file is overwritten (no versions in MVP), so an old
rejected review may talk about text that no longer exists.

## Open questions

1. ~~Full source text~~ Decided: temporary text cache (files in
   `data/cache/pages/`, not in the DB). A cache record keeps the exact
   text until verification is done, then it is deleted. Media (images,
   PDF pages...) later. Note: a revision after a rejected review must
   read the source again.
2. ~~Sources that are not web pages~~ Decided: a local file is a source
   with `kind = file`; its name (with part of the path) is shown, so the
   user sees which workspace files were used. Verification uses the same
   text cache.
3. ~~Same page in many works~~ Decided 2026-09-28: two `work_sources`
   rows is fine for MVP. A global `sources` table maybe later.
4. ~~Review comment~~ Decided: required only for `rejected` (the
   `revise` steps need it).
5. ~~Workspace model~~ Decided 2026-09-28: a workspace is a lab with
   many tasks, task : work = 1 : 1. See `workspaces.md`.
6. ~~Claim with two sources~~ Decided: two `quotes` rows with the same
   `claim` text, OK for MVP. A `claims` table maybe later.
7. **`AGENTS.md` / `ARCHITECTURE.md`** still name `claims` →
   `claim_evidence` → `sources`. Update them when this group is decided.
8. **Delete rule for works and publications.** For now `works.task_id`
   is `CASCADE`. A work (and even more a publication) is not strongly
   tied to its task: people who can see the task see the work. But if a
   task is deleted, its publication disappears too. Review in a later
   iteration (`RESTRICT` on `publications.work_id` is one option).
9. ~~Acceptance when the reviewer is deleted~~ Decided: the `accepted`
   row stays (with `reviewer_id` NULL), the work stays accepted.
10. **Later:** publication reviews, withdrawing a publication,
    materials as folders, work versions.
