# Deploy (test server)

Server: `master@192.168.0.101` (Ubuntu, GTX 1650 4 GB). Login with an SSH
key only. Files: `compose.server.yaml`.

What runs where:

| Part | Where |
|---|---|
| PostgreSQL 16 | existing container `postgres` (`/opt/postgres`), database `autolab`, role `autolab_app` |
| Ollama | on the host (systemd), port 11434 |
| api, worker, MongoDB, SearxNG | `~/autolab`, `docker compose -f compose.server.yaml` |

Open **`http://192.168.0.101:8000`** in a browser: the API also serves the
web app (built into the image), so the app and the API share one address.
API docs: `http://192.168.0.101:8000/docs`. Local network only, no HTTPS
yet.

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
   # Plain HTTP on the home network: without this the browser drops the
   # refresh cookie and you are logged out after 15 minutes or a reload.
   # Remove it when HTTPS exists.
   COOKIE_SECURE=false
   ```
   No `CORS_ORIGINS` needed: the app comes from the same address as the
   API.
4. `mkdir -p data && docker compose -f compose.server.yaml up -d --build`
5. Point the ollama provider to the host (once):
   ```bash
   docker exec -i postgres psql -U admin -d autolab <<SQL
   UPDATE model_providers SET base_url = 'http://host.docker.internal:11434' WHERE name = 'ollama';
   SQL
   ```
6. First admin: sign up in the app, then
   `docker compose -f compose.server.yaml exec api autolab create-admin <user_id>`
   (user 1 is the first account).
7. Add a model in the app: **Admin → Models → Add model** (for example
   `qwen2.5:3b`, context 32768), and pull it on the host:
   `ollama pull qwen2.5:3b`.

## Update

```bash
cd ~/autolab && git pull
docker compose -f compose.server.yaml up -d --build   # migrations run first
```

The image build also builds the web app (Node stage in the `Dockerfile`),
so the first build after a frontend change takes a minute longer.

## Keep the server alive: limits for Ollama

A big model (14B and more, mostly on CPU) can take all CPU and RAM. These
limits keep the server usable: Ollama is slowed down, or killed and
restarted, instead of the whole machine freezing. They need sudo, so run
them yourself:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/limits.conf >/dev/null <<'LIMITS'
[Service]
# One model in memory and one request at a time (the worker sends one
# call at a time anyway); unload a model after 10 idle minutes.
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_KEEP_ALIVE=10m"
# At most 9 of 12 CPU threads: SSH, Postgres and the API stay responsive.
CPUQuota=900%
# RAM: 14 GB total, about 2.5 GB for everything else. Above MemoryHigh
# the kernel slows Ollama down; at MemoryMax Ollama is killed (systemd
# starts it again), and the server lives.
MemoryHigh=10500M
MemoryMax=11500M
# Lower priority than everything else.
Nice=10
IOWeight=50
LIMITS
sudo systemctl daemon-reload
sudo systemctl restart ollama
systemctl show ollama -p CPUQuotaPerSecUSec -p MemoryHigh -p MemoryMax
```

Check: run a task with a 14B model and watch `top` and `free -h`; SSH
should stay fast. A model that needs more memory than `MemoryMax`
(mistral-small:22b needs about 9.5 GB of RAM besides the GPU) fails its
calls, and the step says "the model did not answer". To undo: delete
`limits.conf`, then `daemon-reload` and restart.

## Look around

```bash
docker compose -f compose.server.yaml ps
docker compose -f compose.server.yaml logs -f worker
```
