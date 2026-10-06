# Workspaces (draft, changes to Group 1)

Working notes. Rewritten from the author's Russian draft
(`workspaces.ru.md`, 2026-09-28). Items marked **(proposal)** are
Claude's suggestions and are not decided yet.

Last updated: 2026-09-28

## User story

1. A user wants to research a topic they have no material on.
2. They create a workspace with any name. At first only they can see it.
3. Right after that they create the first task: pick a pipeline, give
   the task a name, and write the request.
4. The owner can invite people to the workspace at any time and later
   assign them to tasks (for example, as reviewer).

## A workspace is a lab

The project is called a "lab", so a workspace is a lab too. It is not
tied to one research:

- A workspace holds any number of tasks.
- Each task produces one **material** (`works`, see
  `results_and_evidence.md`). Task and work are 1 : 1.
- Later: a new task can use materials that already exist in the
  workspace. This will be described in the pipeline YAML files, not now.

## Visibility and archive

Visibility and archive are two separate things.

- **Visibility:** `private` or `public`.
  - A new workspace is `private` by default, but it can be created as
    `public`.
  - **Public once, public forever.** `public → private` is not allowed.
  - In a public workspace, everyone can see all materials.
- **Archive:** a workspace is active or archived (`archived_at`).
  - **Private archive:** the owner keeps the workspace, nobody else sees
    it.
  - **Public archive:** the creator stays the creator, but loses the
    owner status (`owner_id` becomes NULL, a "free project" from
    Group 1). Other people can view it, use its materials, or **take
    it**: the new person becomes the owner, the workspace becomes active
    again, and it stays public. Nothing is copied.

| | active | archived |
|---|---|---|
| private | owner works in it | only the owner sees it |
| public | owner works in it, everyone can see | no owner; anyone can view or take it |

Later: importing materials, transferring rights.

## Changes to `workspaces` (proposal)

| Column | Type | Null | Notes |
|---|---|---|---|
| created_by | bigint | yes | **new**, → users, `SET NULL`; never changes (creator ≠ owner) |
| owner_id | bigint | yes | unchanged; NULL = free (public archived) workspace |
| visibility | text | no | CHECK: **new**, `private` / `public`, default `private` |
| archived_at | timestamptz | yes | unchanged |

Rules:
- `public → private` is blocked. A `CHECK` cannot see the old value, so
  this needs a trigger (`BEFORE UPDATE`) or backend code. Trigger is
  safer (one place, no code path can skip it).
- Archiving a public workspace sets `owner_id = NULL` (backend or
  trigger).

## Open questions

1. ~~Old members~~ Decided 2026-09-28: archiving a workspace (private
   or public) deletes all its `memberships` rows. Later: a membership
   history. Links like `tasks.reviewer_id` / `created_by` stay.
2. ~~Two people take at once~~ Decided: one
   `UPDATE workspaces SET owner_id = :me WHERE id = :id AND owner_id IS NULL
   AND visibility = 'public' AND archived_at IS NOT NULL`;
   0 rows updated = someone was first. The extra checks were added on
   2026-10-05: `owner_id` is also NULL after the owner's account is
   deleted, and such a private workspace must not be free.
