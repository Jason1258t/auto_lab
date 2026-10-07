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
  pages/     one slice per page (login, signup, workspaces, ...)
  widgets/   big blocks made of features and entities (app-header, auth-layout)
  features/  user actions (auth forms, theme-toggle; later: create-task, review)
  entities/  business things and their data (session, workspace; later: task, work)
  shared/    no business logic: api, ui (shadcn atoms), lib, i18n
```

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
