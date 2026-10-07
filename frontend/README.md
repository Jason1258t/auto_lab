# AutoLab frontend

Vite + React 19 + TypeScript. How to run it with the backend: `../DEVELOPMENT.md`.

```bash
npm run dev        # http://localhost:5173 (passes /api to the API on :8000)
npm test           # Vitest + Testing Library + MSW (fake backend)
npm run typecheck
npm run lint       # oxlint
npm run build
npm run api:types  # after a backend API change (needs uv in the repo root)
```

## Structure: Feature-Sliced Design, light version

```
src/
  app/       providers, routes, layouts, global styles: wires everything together
  pages/     one slice per page
  widgets/   big blocks made of features and entities
  features/  user actions (a button, a form, a dialog that changes data)
  entities/  business things: their data hooks and how they look
  shared/    no business logic: api, ui (shadcn atoms), lib, i18n
```

What is where (2026-10-07):

| Layer | Slices |
|---|---|
| pages | `login`, `signup`, `workspaces`, `workspace`, `task`, `work`, `feed`, `publication`, `publisher`, `admin`, `not-found` |
| widgets | `app-header`, `auth-layout`, `workspace-tasks`, `workspace-works`, `workspace-files`, `workspace-members`, `workspace-activity` |
| features | `auth`, `theme-toggle`, `workspace-form`, `workspace-actions`, `member-add`, `member-manage`, `file-upload`, `file-actions`, `task-form`, `task-actions`, `task-review`, `publish-work`, `remove-publication`, `admin-models`, `admin-providers`, `admin-admins` |
| entities | `session`, `workspace`, `member`, `file`, `task`, `call`, `work`, `review`, `publication`, `catalog`, `activity`, `admin` |

Routes (`app/routes/AppRoutes.tsx`): login needed for `/`, `/tasks/:id`,
`/admin`; open to everyone for `/workspaces/:id`, `/works/:id`, `/feed`,
`/publications/:id`, `/publishers/:id` (the backend decides what a
visitor may see).

Rules:

1. **Imports only go down:** app → pages → widgets → features → entities →
   shared. A slice never imports a slice of the same layer.
2. **Import a slice only through its `index.ts`** (its public API):
   `import { useSession } from '@/entities/session'`, not a file inside it.
3. Segments (`ui/`, `model/`, `api/`) inside a slice are optional: use them
   when a slice grows past a few files.
4. `shared/ui` holds the atoms: shadcn/ui components, copied into the repo
   (`npx shadcn@latest add <name>`). Change them freely.
5. Tests sit next to the code (`*.test.tsx`). Test helpers and the fake
   backend are in `src/test/` (outside the layers).

## Conventions

- **API types are generated** from the backend (`shared/api/schema.d.ts`);
  never write API types by hand. CI fails if they are out of date.
- **Every text goes through i18next** (`shared/i18n/en.json`), even with
  English only. Russian later = one more JSON file.
- **Errors:** `call()` turns any API error into an `ApiError`; show it with
  `errorText(error)`. Known codes can get a nicer text in `errors.*`.
- **Tokens:** the access token lives only in memory (`shared/api/client.ts`);
  the refresh token is an httpOnly cookie. Never put tokens in localStorage.
- **Theme:** colors only from the CSS variables in
  `app/styles/index.css` (light and dark), never fixed colors in components.
- **Rights:** `workspaceRights()` in `entities/workspace` mirrors
  `services/permissions.py` to hide buttons a user cannot use. The
  backend still checks everything; keep both in sync.
- **Untrusted text:** model output and web quotes go through
  `shared/ui/markdown.tsx` (no raw HTML) or plain text; never
  `dangerouslySetInnerHTML`.
- **Live data:** a task polls every 3 s while queued or running
  (`refetchInterval` in `entities/task`).
- **Tests:** whole pages against a fake backend (`src/test/server.ts`).
  Node's `FormData`/`File` replace jsdom's in `src/test/setup.ts`, so
  uploads work.
