# Backlog (after MVP)

Features we decided to build later. Design questions that are still
open live in `drafts/schema_design.md` ("Parked for later").

## Tasks and pipelines

- `schedules`: repeat a task by time.
- Per-step model override.

## Results and publications

- Publication reviews.
- Withdrawing a publication.
- Work versions.
- Materials as folders.
- Global `sources` and `claims` tables.

## Audit and logging

- Reports as SQL views: model load, failures, pipeline quality,
  activity (`drafts/audit.md`).
- Subtype tables for `activity_events`.
- Admin page that reads system logs.
- System logs in the same log store as LLM logs.
