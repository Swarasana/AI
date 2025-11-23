# Swarasana AI Summarization Microservice

Production-ready FastAPI microservice that generates inclusive, empathetic Indonesian summaries from recent visitor comments using Gemini 2.5 Flash and Supabase (Postgres). Implements a cost-efficient Stale-While-Revalidate flow.

## Features
- Async FastAPI with cached async Supabase client
- Stale-While-Revalidate freshness check to avoid unnecessary AI calls
- Gemini 2.5 Flash integration with robust error handling
- Clean environment management via Pydantic Settings

## Tech Stack
- Python 3.10+
- FastAPI (async)
- Supabase (supabase-py async)
- Google Generative AI (Gemini 2.5 Flash)
- Pydantic Settings, python-dotenv
- Deployable on Google Cloud Run (stateless)

## Project Structure
```
requirements.txt
.env.example
app/
  core/config.py
  services/
    supabase_client.py
    ai_service.py
  api/routes.py
main.py
```

## Environment Variables
Use `.env` (not committed) for real values. The service expects these variables:

```
SUPABASE_URL="<your-supabase-project-url>"
SUPABASE_KEY="<your-supabase-anon-or-service-role-key>"
GEMINI_API_KEY="<your-google-generativeai-api-key>"
```

Notes:
- Only define `SUPABASE_URL` once; do not duplicate keys or URLs.
- This code uses `SUPABASE_KEY` as the key name. If you prefer `SUPABASE_ANON_KEY`, either set both to the same value or update `app/core/config.py` to use `SUPABASE_ANON_KEY`.
- Never store real secrets in `.env.example`. Put real secrets in `.env` locally or as environment variables in Cloud Run.

## Virtual Environment Setup
Create a local virtual environment to isolate dependencies and speed up installs.

```
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Deactivate with `deactivate`. Re-activate with `source .venv/bin/activate`.

## Run Locally
1. Create `.env` with your values.
2. Start the API:

```
uvicorn main:app --host 0.0.0.0 --port 8000
```

3. Test endpoint (replace `collection_id` with a UUID):

```
curl -X POST http://localhost:8000/api/v1/summarize/<collection_id>
```

## Run with Docker

### Prerequisites
- Docker and Docker Compose installed
- `.env` file with required environment variables

### Quick Start

1. **Create `.env` file** (if not exists):
```bash
SUPABASE_URL="<your-supabase-project-url>"
SUPABASE_KEY="<your-supabase-anon-or-service-role-key>"
GEMINI_API_KEY="<your-google-generativeai-api-key>"
```

2. **Build and run with Docker Compose:**
```bash
docker-compose up --build
```

3. **Run in detached mode (background):**
```bash
docker-compose up -d --build
```

4. **View logs:**
```bash
docker-compose logs -f
```

5. **Stop the service:**
```bash
docker-compose down
```

### Docker Commands

**Build image only:**
```bash
docker build -t swarasana-ai:latest .
```

**Run container manually:**
```bash
docker run -d \
  --name swarasana-ai \
  -p 8000:8000 \
  --env-file .env \
  swarasana-ai:latest
```

**Check container status:**
```bash
docker ps
docker logs swarasana-ai
```

### Docker Compose Configuration

The `docker-compose.yml` includes:
- Automatic restart policy
- Health checks
- Environment variable management
- Port mapping (8000:8000)
- Network isolation

## Endpoint Behavior (Stale-While-Revalidate)
- Reads `collections.ai_summary_text` and `collections.last_summary_generated_at`.
- Reads latest `comments.created_at` for the collection.
- If existing summary is newer than the newest comment, the service returns the cached summary immediately (no AI call).
- Otherwise fetches the latest 50 comments; if fewer than 3, returns `{"summary": "Belum cukup data untuk merangkum."}`.
- If enough comments, calls Gemini 2.5 Flash, updates `collections.ai_summary_text` and `collections.last_summary_generated_at`, and returns the new summary.

## Key Code References
- Settings and env management: `app/core/config.py:5–15`
- Supabase async client and DB ops: `app/services/supabase_client.py:14–21`, `31–43`, `46–59`, `62–73`, `76–84`
- Gemini service and async generation: `app/services/ai_service.py:13–20`, `23–33`
- FastAPI route implementing freshness logic: `app/api/routes.py:19–42`

## Deploy to Google Cloud Run (Source Deploy)
Prerequisites:
- `gcloud` CLI authenticated and project selected
- Enable Cloud Build and Cloud Run APIs

Deploy using source-based build:
```
gcloud run deploy swarasana-summarizer \
  --source . \
  --region <your-region> \
  --allow-unauthenticated \
  --set-env-vars SUPABASE_URL=<url>,SUPABASE_KEY=<key>,GEMINI_API_KEY=<gemini_key>
```

Cloud Run will build the container, deploy it, and provide a public HTTPS URL. Use the same `/api/v1/summarize/{collection_id}` endpoint.

## Security
- Treat Supabase keys and Gemini API key as secrets.
- Rotate any leaked keys immediately in the Supabase and Google consoles.
- Do not commit `.env` with real values.

## Troubleshooting
- 404 on summarize: ensure the `collection_id` exists in `collections`.
- 502 AI error: check `GEMINI_API_KEY`, network egress, and quotas.
- Empty responses: confirm there are at least 3 comments for the collection.