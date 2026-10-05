# Auth (draft, Group 6)

Working notes. Rewritten from the author's draft (`auth.ru.md`,
2026-10-05).

Last updated: 2026-10-05

## Main idea

Three separate things, three separate tables:

- **Who the person is:** `users` (Group 1).
- **How they prove it:** `password_credentials` now, `user_identities`
  for external providers later.
- **Proof that they are logged in now:** `sessions`.

MVP: email + password only. GitHub / Google login is designed now, so
adding it later does not change other tables.

## Change to Group 1: users

New column:

| Column | Type | Null | Notes |
|---|---|---|---|
| email_verified | boolean | no | default `false`; no code for it in the MVP |

It lives in `users` because it describes the email, and the email lives
in `users`. Later a Google login can verify the same email.

## password_credentials

| Column | Type | Null | Notes |
|---|---|---|---|
| user_id | bigint | no | PK, → users, `CASCADE` (one password per user) |
| password_hash | text | no | argon2; never the password itself |
| updated_at | timestamptz | no | default `now()` |

Login uses `users.email`, so the email is not stored twice.

## user_identities (designed now, built later)

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| user_id | bigint | no | → users, `CASCADE` |
| provider | enum | no | `github` / `google` |
| provider_user_id | text | no | the user's id at that provider |
| created_at | timestamptz | no | default `now()` |

Unique: `(provider, provider_user_id)`.

## admins

Being in this table means being an admin.

| Column | Type | Null | Notes |
|---|---|---|---|
| user_id | bigint | no | PK, → users, `CASCADE` |
| granted_at | timestamptz | no | default `now()` |
| granted_by | text | yes | plain text for now, no FK |

Granting and removing admin rights are written to `activity_events`
(`admin_granted`, `admin_revoked`).

## sessions

Usual access + refresh token scheme:

- **Access token:** short JWT (about 15 minutes), not stored in the DB.
- **Refresh token:** stored only as a hash. Each refresh replaces it
  with a new one (rotation).
- After logout, an old access token keeps working until it expires
  (up to about 15 minutes). This is accepted.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| user_id | bigint | no | → users, `CASCADE` |
| refresh_token_hash | text | no | unique |
| created_at | timestamptz | no | default `now()` |
| expires_at | timestamptz | no | |
| last_used_at | timestamptz | yes | |
| revoked_at | timestamptz | yes | NULL = active (logout sets it) |

## Deleting a user

- `password_credentials`, `user_identities`, `admins`, `sessions`,
  `memberships`: `CASCADE`.
- Old `activity_events` rows keep their copied names.
- A global `user_deleted` event (admins only) keeps the user's id and
  username. No email: keeping the email of a deleted person in a log
  that is never cleaned works against the point of deleting them.

## What we do not do now

- **One-time tokens** (email confirmation, password reset): none. An
  admin resets passwords by hand. Password reset is in `BACKLOG.md`.
- **Account linking** (Google login with an email that already exists):
  later, we have one provider.
- **Invites:** none. The owner adds people to a workspace directly, so
  Group 1 does not change.
- **Secret store** (API keys for model providers): still open. Only
  admins and the system can read it. Probably not Postgres; `.env` for
  the MVP.

## Logging

- `activity_events`: `admin_granted`, `admin_revoked`, `user_deleted`
  (global, `workspace_id = NULL`).
- Logins and failed logins are not tracked in the DB. System logs only.
