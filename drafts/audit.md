# Audit and logging (draft, Group 5)

Working notes. Rewritten from the author's draft (`audit.ru.md`,
2026-10-04). Items marked **(proposal)** are Claude's suggestions and
are not decided yet.

Last updated: 2026-10-05

## What we track, and where

| What | Where | MVP? |
|---|---|---|
| Important human actions (workspace and admin) | `activity_events` table | yes |
| Copies of deleted or changed rows | not stored | no |
| LLM calls and their results | `llm_calls`, `llm_responses` (Group 3) + log store | yes (done) |
| Technical errors and system logs | files outside the DB | yes |
| Reports (model load, failures, quality) | SQL views | after MVP |

Why no copies of deleted rows: they take up a lot of space with many
users, and the app does not use them. For debugging, the PostgreSQL
server log is enough.

## activity_events

An audit log like in Discord servers or Telegram channels: who did what,
to what, and where. It is a fixed list of actions, not a copy of every
changed row. This keeps it small and easy to read.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| occurred_at | timestamptz | no | default `now()` |
| actor_id | bigint | yes | user who did it; **no FK**, so the row survives when the user is deleted; NULL = the system |
| actor_name | text | yes | copy of the user's name at that moment |
| workspace_id | bigint | yes | **no FK**, same reason; NULL = global action (admin, publisher) |
| action | text | no | CHECK: see the list below |
| target_type | text | yes | CHECK: `workspace` / `membership` / `task` / `work` / `publication` / `publisher` / `user` |
| target_id | bigint | yes | id of the changed object |
| target_label | text | yes | copy of its name at that moment (task title, user name...) |
| details | jsonb | yes | extra data, e.g. `{"role": "reviewer"}` |

Why name copies: the log must still read well after the user or task is
gone ("Ivan gave Bob the reviewer role", not "user 17 ... user 23").

Index **(proposal)**: `(workspace_id, occurred_at DESC)` for the
workspace log page.

### Actions (first list, not final)

- Workspace: `member_added`, `member_removed`, `role_added`,
  `role_removed`, `workspace_taken`, `made_public`, `archived`,
  `task_deleted`, `work_published`.
- Global: `publisher_created`, `admin_granted`, `admin_revoked`,
  `user_deleted` (id and username only, no email; see `auth.md`).

`task_deleted` logs the event (who, which task, its title), not a copy
of the task row.

### Who can read it

- Workspace log (`workspace_id` is set): the owner and editors.
- Global events (`workspace_id` is NULL): admins only.

### Later: subtype tables

The author's idea: `activity_events` is the base ("log body"), and some
areas get their own table with real columns, where the PK is also an FK
to `activity_events.id` (supertype/subtype pattern). Not now: for the
MVP, `details jsonb` is enough. Add a subtype table when an area needs
real columns and constraints.

## Errors shown to users

- `llm_calls.error` stays a short message that is safe to show to the
  user.
- The full details (traceback, raw response) are in the system logs.
  Every log line carries `call_id` / `task_id`, so an admin can find the
  details by that id. No new column is needed.

## System logs (outside the DB)

They can't live in PostgreSQL: if the DB is down, the error that
explains it can't be saved there.

- Python `logging`, one JSON object per line.
- `TimedRotatingFileHandler`: a new file every day, old files deleted
  after N days.
- A second handler writes only `ERROR` and above (with full traceback)
  to a separate errors file. One errors file, not one file per crash:
  that is easier to search.
- Every line has context fields where they exist: `task_id`, `call_id`,
  `user_id`.
- Later: the same log store as LLM logs (`backend/log_store.py`), and
  an admin page that reads them.

## Reports (SQL views, after MVP)

No new tables, the data is already there.

- **Model load:** calls, tokens, average queue wait and run time, per
  model per day (`llm_calls` + `llm_responses`).
- **Failures:** share of `failed` calls and invalid JSON, per model.
  Shows which model is too weak for which step.
- **Pipeline quality:** accepted vs rejected reviews and the average
  number of `revise` rounds, per pipeline version.
- **Activity:** tasks per workspace, publications per publisher.

## Admin

Admin = a row in the `admins` table (Group 6, `auth.md`), kept apart
from the main `users` table. Admin actions are written to `activity_events` with
`workspace_id = NULL`.

## Open questions

- Who writes `activity_events`: the backend, in the same transaction as
  the action **(proposal)**, or DB triggers? Triggers can't see who the
  actor is without extra session settings.
- How long to keep `activity_events` rows (forever, or N months)?
- Should members see the log of a public workspace too?
