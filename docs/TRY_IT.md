# Try it: a 20-minute tour

A step-by-step test of the whole app, with what you should see. Use it
to check a new version, and to write feedback. Words and rules:
`docs/USER_GUIDE.md`.

## Before you start

- The app runs: on the test server `http://192.168.0.101:8000` (see
  `DEPLOY.md`), or locally `http://localhost:5173` (see `DEVELOPMENT.md`;
  a real run needs the worker and Ollama).
- You are an admin, and at least one model is **available**
  (Admin → Models). On the server: `qwen2.5:3b`.
- For the roles part: a second account. Open a private browser window
  for it.

Write down anything that is wrong, unclear or slow, with the step number
(a template is at the end).

## 1. Account

1. Open the app. You see **Log in**.
2. **Sign up** with a new account. → You are logged in and see
   *Workspaces* with "No workspaces yet".
3. Reload the page. → You are still logged in.

## 2. Workspace

4. **New workspace**: name "Sky research", a description. → The
   workspace page opens. Facts: *Private · Owner*. Tabs: Tasks, Works,
   Files, Members, Activity.
5. **Edit**: change the description. → The new text shows at once.

## 3. People and roles

6. In the private window, sign up as a second person (for example
   `bob`).
7. Back as the owner: **Members** → add `bob`. → Bob appears with the
   checkboxes *Editor* and *Reviewer*, and his id.
8. Tick **Reviewer** for Bob.
9. As Bob, open the workspace (Workspaces → Mine). → Bob sees the tabs
   but no *New task*, no *Upload*, no *Activity*.

## 4. Files

10. As the owner: **Files → Upload files**, choose one or two small
    files. → They are listed with size and date. **Download** works.

## 5. A task

11. **Tasks → New task**: title "Why is the sky blue?", task "Explain
    why the sky is blue in the day and red at sunset.", reviewer: Bob.
    → The task page opens: status *Draft*, 7 waiting steps (plan, search,
    fetch, summarize, verify, synthesize, write).
12. **Queue**. → *Queued*, then *Running* (when the worker takes it).
    Watch the steps turn to done one by one, with summaries and times.
    No reload needed.
13. Under *plan*, open the **model call**. → You see the system prompt,
    the prompt with your task, the expected JSON shape, and the answer.
14. After about 2 minutes: *In review*. → **Result** shows the text,
    maybe some **(⚠ no source)** marks with a warning, and **Sources and
    quotes**. Open a source link: the quote should be on that page.

## 6. Review

15. As Bob: open the task. → The **Review** card. *Reject and run
    again* is off until you write a comment.
16. Write "Add a source for every sentence" and **Reject**. → The task
    goes back to *Queued*. New steps appear under *Revision after a
    rejected review*. Only the last steps run again.
17. When it is *In review* again: **Accept**. → *Done*.

## 7. Publish

18. As the owner: **Publish** → *New publisher…*, name "Sky Lab",
    keep the title, **Publish**. → The publication page opens.
19. Log out (or use the private window logged out): **Feed**. → The
    publication is listed. The publication and publisher pages open
    without an account.

## 8. Public and archive

20. As the owner: **Make public**. As Bob or logged out, open the
    workspace. → Visitors see only its accepted works.
21. **Archive** the public workspace. → It is read-only and has no owner.
    As Bob: Workspaces → **Free to take** → open it → **Take**. → Bob is
    the owner now.

## 9. Admin

22. **Admin → Models**: untick *Available* for a model. → It is gone
    from *New task*. Tick it again.
23. **Admin → Activity**: you see the admin and publisher events.
24. On the publication page: **Remove from the feed**. → The feed no
    longer lists it.

## Feedback template

```
Step: 14
What I did: opened the second source link
What I expected: the quote is on the page
What happened: the page is a cookie banner, no quote visible
How bad: small / annoying / blocks me
Idea (optional): show the date the page was read next to the link
```

Also useful: screenshots, the task id (in the address: `/tasks/12`), and
the time it happened.
