# Production deployment

This deployment keeps the Vite frontend on Vercel and runs the API and Celery
worker on Render. PostgreSQL is the Render-managed database and Upstash Redis
is used by both the API and worker.

## 1. Prepare providers

1. Rotate any credentials that have ever been placed in a local `.env`.
2. Create a Render PostgreSQL database and copy its internal or external
   `DATABASE_URL` as appropriate for the service.
3. Create an Upstash Redis database and use its `rediss://` connection URL as
   `REDIS_URL`.
4. Create a Render Web Service from the repository using the Dockerfile
   `backend/Dockerfile`.
5. Create a Render Background Worker from the same repository using
   `backend/worker.Dockerfile`.

## 2. Render Web Service

Set the service environment variables:

```text
DATABASE_URL=<Render PostgreSQL URL>
REDIS_URL=<Upstash Redis URL>
JWT_SECRET=<unique random value of at least 32 characters>
CORS_ORIGINS=https://<your-vercel-project>.vercel.app
FRONTEND_URL=https://<your-vercel-project>.vercel.app
GROQ_API_KEY=<server-side Groq key>
GROQ_MODEL=openai/gpt-oss-120b
TAVILY_API_KEY=<server-side Tavily key>
GOOGLE_BOOKS_API_KEY=<optional server-side key>
YOUTUBE_API_KEY=<optional server-side key>
OPENALEX_MAILTO=<optional contact address>
CROSSREF_MAILTO=<optional contact address>
```

The Dockerfile runs `alembic upgrade head` before Uvicorn and binds to
`0.0.0.0:$PORT`. Use the Render health check path `/health`.

## 3. Render Background Worker

Use the Dockerfile `backend/worker.Dockerfile`. Give it the same
`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, provider keys, and model settings
as the web service. The worker command is defined by the Dockerfile:

```text
celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

The worker must use the same Redis URL as the API. Do not put these variables
in the frontend or Vercel project.

## 4. Vercel frontend

Create a Vercel project with `frontend` as the root directory. Set only:

```text
VITE_API_URL=https://<your-render-web-service>.onrender.com
```

The Vite build reads `VITE_API_URL`; the local fallback is used only when this
variable is absent during development. Add the final Vercel origin to
`CORS_ORIGINS` and redeploy the backend if the Vercel domain changes.

## 5. Migration and health checks

The web container applies migrations automatically. For a manual migration
from a trusted environment:

```powershell
Set-Location backend
alembic upgrade head
```

The current migration head is `0004_user_full_name`. Verify:

```text
GET https://<your-render-web-service>.onrender.com/health
```

Expected response:

```json
{"status":"ok"}
```

## 6. Production checklist

- [ ] Rotate all development/provider credentials.
- [ ] Confirm `.env` is not tracked.
- [ ] Configure Render PostgreSQL and Upstash Redis.
- [ ] Set a strong unique `JWT_SECRET`.
- [ ] Set production `CORS_ORIGINS` and `FRONTEND_URL`.
- [ ] Run or verify Alembic migrations.
- [ ] Verify web-service `/health`.
- [ ] Verify the worker connects to Redis.
- [ ] Set Vercel `VITE_API_URL`.
- [ ] Test registration, login, refresh, logout, lesson ownership, generation,
      QC, editing, preview, and exports.

PDF, DOCX, and QC report exports are generated in memory from PostgreSQL data
and downloaded on demand. The application does not write generated files to a
container filesystem, so Cloudflare R2/S3 is not required for the current
export workflow. If a future feature adds persistent uploads or stored export
artifacts, add an owner-scoped S3-compatible storage adapter and authorization
checks before enabling it.
