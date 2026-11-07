# AI Lesson Studio

AI Lesson Studio is a full-stack lesson design workspace. The React + TypeScript client connects to a FastAPI API. The platform researches websites, books and YouTube videos, generates source-grounded lessons with Groq, runs two independent quality reviews, records instructor revisions, and exports the final lesson and QC reports.

## Features

- Instructor registration, login, JWT-protected routes, Argon2 password hashing and optional one-time password reset links through SMTP.
- Dashboard with database-backed counts, drafts, reviews, completed lessons and recent activity.
- Tavily, Google Books, OpenAlex, Crossref and YouTube Data API research; accessible public webpages are extracted where possible. Provider provenance, canonical identifiers, metadata-only records and partial availability are preserved.
- Groq structured JSON generation for lessons and quality reviews.
- Celery and Redis background tasks with progress and failure polling.
- PostgreSQL models and Alembic migration for users, lessons, sections, sources, QC reports/issues, recommendations, revisions and tasks.
- Two independent QC services run in parallel: factual accuracy receives research evidence, while instructional quality receives only lesson design inputs. Their reports and statuses are persisted separately; one failure never deletes the other report.
- Lesson editor, preview, source filtering, recommendation apply/reject, revision history and restore.
- PDF and DOCX lesson exports plus independent factual and instructional QC PDF exports.
- Responsive light interface with optional dark theme.
- Backend/API, frontend component and legacy business-module tests.

## Architecture

The React app is in frontend. Vite serves assets; React Router selects views; TanStack Query handles API state and task polling; React Hook Form and Zod validate forms; shadcn-style Button and Card primitives provide reusable UI.

The FastAPI service is in backend/app. Authentication and lesson routes use SQLAlchemy persistence. Celery workers orchestrate research, generation and QC. Existing research, generation, QC and export business logic is reused from modules and utils. PostgreSQL is the application database; Alembic manages migrations.

The browser uses bearer tokens. Lesson, source, QC, task and revision routes check ownership. Password-reset responses do not reveal whether an email belongs to an account.

## Requirements

- Python 3.11 or 3.12.
- Node.js 22 LTS.
- Docker Engine/Desktop with Compose for PostgreSQL, Redis and container deployment.
- A Groq API key and an available Groq chat model.
- Tavily and YouTube keys for those search providers. Google Books may work without a key, subject to quota.

## Local setup on Windows PowerShell

From the project root:

    Copy-Item .env.example .env
    $secret = python -c "import secrets; print(secrets.token_urlsafe(48))"
    Write-Host "Set JWT_SECRET in .env to: $secret"

Edit .env and replace JWT_SECRET with the generated value. Create a key in the [Groq Console](https://console.groq.com/keys), set GROQ_API_KEY, and choose an available [Groq chat model](https://console.groq.com/docs/models). Groq credentials are used only by the backend and worker; they are never sent to the browser.

Start PostgreSQL and Redis:

    docker compose up -d postgres redis

Install Python packages and migrate the database:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Set-Location backend
    alembic upgrade head

In one backend PowerShell window, run the API:

    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

In another backend window, run Celery. The solo pool is suitable for local Windows development:

    Set-Location backend
    celery -A app.celery_app:celery_app worker --pool=solo --loglevel=INFO

The command must run from `backend` (or use Celery's `--workdir=backend` option)
because the `app` Python package is located there. Ensure the root `.env` file
exists and contains a real `JWT_SECRET`; Celery imports the same settings as the
API and will refuse to start without it. From the repository root, the equivalent
command is:

    celery --workdir=backend -A app.celery_app:celery_app worker --pool=solo --loglevel=INFO

In another window, run the React app:

    Set-Location frontend
    npm ci
    npm run dev

Open http://localhost:5173. Create an instructor account and a lesson. API documentation is at http://localhost:8000/docs.

## Environment variables

- DATABASE_URL: PostgreSQL SQLAlchemy URL. Compose supplies the container hostname.
- REDIS_URL: Celery broker/backend URL.
- JWT_SECRET: Required unique random value of at least 32 characters. Do not use the example placeholder.
- JWT_EXPIRE_MINUTES: Access-token lifetime; defaults to 720.
- CORS_ORIGINS: Comma-separated browser origins allowed by FastAPI.
- GROQ_API_KEY and GROQ_MODEL: Groq credentials and model used for generation and both QC calls. Keep the key in the root .env file; do not add it to frontend variables or log it.
- GROQ_TIMEOUT: per-request timeout in seconds; defaults to 120.
- GROQ_MAX_RETRIES: bounded retries for rate limits, transient server errors and connection timeouts; defaults to 2. HTTP 429 responses honor Retry-After up to 60 seconds.
- GROQ_MAX_COMPLETION_TOKENS and GROQ_QC_MAX_COMPLETION_TOKENS: output limits for lesson generation and each QC report, respectively. Defaults (2,500 and 1,400) keep requests within common Groq free-tier token limits while allowing larger values for accounts with higher limits.
- TAVILY_API_KEY, GOOGLE_BOOKS_API_KEY, YOUTUBE_API_KEY: research credentials.
- OPENALEX_MAILTO, CROSSREF_MAILTO: optional polite-pool contact addresses for scholarly APIs.
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM: optional password-reset email delivery.
- FRONTEND_URL: base URL used for reset links.

Never commit .env or API credentials.

## Research and lesson workflow

1. An instructor creates a saved draft with title, objective, audience and difficulty.
2. The API queues research and generation and returns a task ID.
3. A worker gathers real provider sources, stores them, extracts accessible webpage text and generates a lesson with references and a time plan validated to 45 minutes.
4. Factual QC checks lesson claims against retrieved evidence. Instructional QC separately reviews objective alignment, clarity, structure, relevance and assessment.
5. Instructors edit, preview, apply/reject recommendations and restore earlier revisions.
6. PDF/DOCX lesson exports and a separate QC export remain available.

Generation stops when no genuine research source is available. QC is advisory and does not guarantee correctness.

## Tests and validation

Run API and existing business-module tests from the project root:

    pytest -q

Run frontend tests and a production build:

    Set-Location frontend
    npm test
    npm run build

Automated provider tests use mocks. The two exact assignment title/objective samples also run through the API, worker pipeline, both QC layers, revision editing and exports in a mocked end-to-end test. Mock sources exist only in test code. Production/local app persistence is PostgreSQL; API tests use isolated SQLite databases.

The HTTP Requests and Responses sample has been verified end to end with live Groq calls, available research providers, and both independently persisted QC reports. The Introduction to Machine Learning sample remains covered by mocked end-to-end tests; live source availability depends on provider credentials and quotas.

## Docker Compose

Copy and configure .env as described above, then run:

    docker compose up --build -d
    docker compose ps
    docker compose logs -f backend worker

The API container applies Alembic migrations before Uvicorn starts. The production React bundle is served by Nginx at http://localhost:8080. API health is at http://localhost:8000/health.

Stop services while keeping the database volume:

    docker compose down

## Deployment

- Vercel: set the frontend project root to frontend, build command to npm run build, output directory to dist, and VITE_API_URL to the deployed backend. frontend/vercel.json configures SPA fallback.

### Vercel frontend deployment

Deploy the `frontend` directory as the Vercel project root. Vercel will use the
existing Vite build configuration; set the following project environment
variable to the public URL of the separately deployed FastAPI service:

    VITE_API_URL=https://your-api.example.com

Do not put provider keys, database URLs, Redis URLs, or `JWT_SECRET` in Vercel
frontend environment variables. They belong only in the backend/worker runtime.
The backend must allow the deployed Vercel origin through `CORS_ORIGINS`, for
example:

    CORS_ORIGINS=https://your-frontend.vercel.app

Before pushing to GitHub, verify that `.env`, `DEMO_CREDENTIALS.txt`, generated
exports, and build artifacts are untracked. The root `.gitignore` excludes
these local-only files; `.env.example` is intentionally retained as the safe
configuration template. Vercel: set the frontend project root to frontend, build command to npm run build, output directory to dist, and VITE_API_URL to the deployed backend. frontend/vercel.json configures SPA fallback.
- Render/Railway: deploy backend/Dockerfile with the repository root as build context. Set managed PostgreSQL, Redis, JWT_SECRET, CORS_ORIGINS and provider settings.
- Worker: deploy backend/worker.Dockerfile with the same database, Redis, provider and model variables.
- Use managed PostgreSQL/Redis and non-example credentials in production.
- Keep Groq and research provider keys in backend/worker environment configuration; never expose them through frontend build variables or logs.
- Configure SMTP and FRONTEND_URL for password recovery.

## Project structure

    backend/app/api/          Auth and REST endpoints
    backend/app/models/       PostgreSQL SQLAlchemy models
    backend/app/schemas/      Pydantic validation
    backend/app/services/     Export helpers
    backend/app/tasks/        Celery pipeline tasks
    backend/alembic/          Migration environment and schema
    backend/tests/             API integration tests
    frontend/src/components/   Shared UI primitives
    frontend/src/App.tsx       Routed instructor experience
    modules/                   Reused research, generation, QC and export logic
    utils/                     LLM provider and validation helpers
    tests/                     Existing business-module tests
    docker-compose.yml         PostgreSQL, Redis, API, worker and frontend

## Known limitations

- Live generation depends on provider credentials/quota and a reachable model.
- Google Books may rate-limit unauthenticated calls; YouTube search does not fetch video transcripts or durations.
- Public page extraction cannot access protected pages.
- Docker images were not launched in this environment because its Docker daemon was unavailable; Compose configuration validation passed.
- Password reset requires SMTP configuration. Recommendations whose section labels cannot be safely mapped remain manual edits.
- The former SQLite module remains for existing business tests; the app uses PostgreSQL. No pre-existing lesson database file was present to migrate.
- Configure HTTPS, secret rotation, production email, backups, monitoring and infrastructure-level rate limiting before public launch.
