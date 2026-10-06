# Deploy (test server)

Server: `master@192.168.0.101` (Ubuntu, GTX 1650 4 GB). Login with an SSH
key only. Files: `compose.server.yaml`.

What runs where:

| Part | Where |
|---|---|
| PostgreSQL 16 | existing container `postgres` (`/opt/postgres`), database `autolab`, role `autolab_app` |
| Ollama | on the host (systemd), port 11434 |
| api, worker, MongoDB, SearxNG | `~/autolab`, `docker compose -f compose.server.yaml` |

The API listens on `http://192.168.0.101:8000` (local network only, no
HTTPS yet). Docs: `http://192.168.0.101:8000/docs`.

## First time

1. Database role (once). The password is generated on the server and
   only written into `~/autolab/.env`:
   ```bash
   docker exec -i postgres psql -U admin -d autolab <<SQL
   CREATE ROLE autolab_app LOGIN PASSWORD '<generated>';
   ALTER DATABASE autolab OWNER TO autolab_app;
   SQL
   ```
2. Code: `git clone https://github.com/Jason1258t/auto_lab.git ~/autolab`
3. `~/autolab/.env` (mode 600):
   ```
   DATABASE_URL=postgresql+psycopg://autolab_app:<password>@postgres:5432/autolab
   JWT_SECRET=<48 random bytes>
   LOG_STORE=mongo
   MONGO_URL=mongodb://mongo:27017
   SEARXNG_URL=http://searxng:8080
   SEARXNG_SECRET=<random>
   CORS_ORIGINS=["http://192.168.0.101:5173"]
   ```
4. `mkdir -p data && docker compose -f compose.server.yaml up -d --build`
5. Point the ollama provider to the host and add a model (once):
   ```bash
   docker exec -i postgres psql -U admin -d autolab <<SQL
   UPDATE model_providers SET base_url = 'http://host.docker.internal:11434' WHERE name = 'ollama';
   SQL
   ```
   Then add models as an admin (`POST /api/v1/admin/models`), or with SQL.
6. First admin: sign up, then
   `docker compose -f compose.server.yaml exec api autolab create-admin <user_id>`.

## Update

```bash
cd ~/autolab && git pull
docker compose -f compose.server.yaml up -d --build   # migrations run first
```

## Look around

```bash
docker compose -f compose.server.yaml ps
docker compose -f compose.server.yaml logs -f worker
```
