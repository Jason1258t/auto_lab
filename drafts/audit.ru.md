
## What we really will track

1) First group - workspace actions. We will create an audit log like in discord servers or telegram channels. Need to add more info about where and what, to easily understand what happened
2) Delete traces - excessive information, and it can eat a lot of space if we have a lot of users. We can't use this information, and in dev purposes we can list the posgre journal.
3) Tech errors and logs, we need to store as files (file like objects, mongo also might be) at this moment. Useful info, but not much to implement powerful storage and backend + ui system
4) Not for mvp for sure

As said, that most of those is overkill for the MVP, but think we already need to start manage document with tasks out of mvp. We have all this points, and more from earlier conversations.

## Ideas

**A. `activity_events`: one small table for important actions** (covers 1, 2, and the "membership history" we parked)

|Column|Notes|
|---|---|
|id, occurred_at||
|actor_id|the user who did it; no FK, so the row survives when the user is deleted|
|workspace_id|no FK, for the same reason|
|action|enum: `member_added`, `member_removed`, `role_changed`, `workspace_taken`, `made_public`, `archived`, `work_published`, `task_deleted`, ...|
|target_type, target_id|what was changed, for example `task` and `42`|
|details|`jsonb`, for example `{"role": "reviewer"}`|

It is a fixed list of actions, not a copy of every changed row. That keeps it small and easy to read.

We would use this as template for audit system entities, which might be different and more specified for dedicated areas. Also may extract "log body" entity with base information, and specified entites will point to it via log_id or smth else.


**B. Reports as SQL views** (covers 4; no new tables, the data is already there)

- **Model load:** calls, tokens, average queue wait and run time, per model per day (`llm_calls` + `llm_responses`).
- **Failures:** the share of `failed` calls and invalid JSON, per model. This shows which model is too weak for which step.
- **Pipeline quality:** accepted vs rejected reviews and the average number of `revise` rounds, per `pipeline_version`. This shows whether version 1.0.2 is better than 1.0.1.
- **Activity:** tasks per workspace, publications per publisher.

We should revise that we clearly gives info about working with model, call, response, failure and failure reason have to be accessible to user. Failure messages might point to the system log file or smth else, user haven't access to it, but we can look what's wrong.

**C. System logs stay outside the DB** (covers 3). Use normal Python logging to files or journald, or later the same log store as for LLM logs. An admin page can read them. If a database is down, the error that explains it can't be saved in that database, so these logs must live outside it.

One my point: we really should customize it, separate files by time, separated log files for each crash. I don't know what normal log systems can, just imho that we should make it clear to use.

## Missing for all of this: an admin

During working on Auth group we will add boolean admin field to the info about user authentification, separated from main user info.
