# ChronicNerd / DietNerd

ChronicNerd is a conversational diet and nutrition research app in the CustomNerd family. The current web UI and assistant are branded **DietNerd**. It helps a signed-in user explore published research, inspect linked sources, and continue questions within saved conversations. It is an exploratory tool, not a medical diagnosis or a substitute for a dietitian.

## What is in this repo

- A FastAPI research API (`dietnerd-backend/`) that searches and processes scientific literature, builds answers, and exposes progress through server-sent events (SSE).
- A responsive, browser-based chat (`dietnerd-website/`) with conversation history, follow-up context, attachment uploads, an in-chat source list and source drawer, a download-answer control, and related saved-question suggestions.
- MySQL-backed user accounts and conversations. Passwords use bcrypt; session tokens are stored as digests in a database table and sent to browsers in HttpOnly cookies. Changing a password revokes other sessions.
- Optional research controls: claim-source ledger and a browser-local answer notebook. These are opt-in display/storage features, not scientific validation. A retrieved source or matched citation does **not** prove an answer's claim.
- Local Docker Compose and automated API/browser tests. The frontend is plain HTML, CSS and JavaScript.

The research pipeline can take time. The chat shows stages and retrieved article titles while work is running; these titles are search context, not verified claim support. SSE reconnects can replay bounded progress from the same running API process, but a process restart can interrupt an in-flight request. Saved conversation turns remain in MySQL.

## Project layout

| Path | Purpose |
| --- | --- |
| `dietnerd-backend/main.py` | FastAPI endpoints, research orchestration, SSE, session-backed conversation routes |
| `dietnerd-backend/helper_functions.py` | Research, PubMed and publisher helpers |
| `dietnerd-backend/auth.py`, `conversation_store.py` | Authentication helpers and atomic turn storage |
| `dietnerd-website/index.html`, `index.js`, `index.css` | Main chat and source UI |
| `dietnerd-website/login.html`, `about.html`, `contact.html`, `addons.html` | Account and supporting pages |
| `scripts/build-s3-site.sh` | Build a static-only site artifact with a configured public API URL |
| `tests/` | API contract, integration, concurrency and browser checks |
| `docs/aws-deployment.md` | Deployment preparation and security decisions, not a record of a completed AWS deployment |

## Run locally

Requirements: Docker with Compose. Copy the example configuration, set your research API credentials, then start the three services:

```bash
cp .env.example .env
# Edit .env with OPENAI_API_KEY, NCBI_API_KEY and any applicable publisher keys.
docker compose up --build
```

Open http://localhost:8080 and create an account. The API health endpoint is http://localhost:8000/health. Compose starts MySQL 8, the API and an nginx static-site server. MySQL uses the named `dbdata` volume. The backend creates its tables at startup.

`dietnerd-website/env.js` is browser-visible configuration, not a secret store; its local default API URL is `http://localhost:8000`. Keep `.env`, keys and database credentials out of version control. Use HTTPS and `COOKIE_SECURE=1` for real deployments. With a separate site/API origin, set `ALLOWED_ORIGINS`, `PUBLIC_SITE_URL` and cookie settings deliberately. A static S3 website over HTTP with a separate HTTP API has **not** been validated as a working authenticated setup.

For local password-reset testing, `.env.example` describes the SES, SMTP and log-only paths. Log-only mode writes reset links to backend logs and is not suitable for a public launch.

## Tests

For the disposable MySQL-backed suite:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
./tests/run_local_mysql_tests.sh
```

The script uses a temporary MySQL 8 container and cleans up its test volume. For browser integration checks, install Node packages and run the browser fixture with the same test database environment:

```bash
npm ci
./tests/run_browser_e2e.sh
node tests/browser_xss_e2e.js
```

The browser fixture stubs external science APIs; it does not prove a live PubMed/OpenAI answer. A release check should cover a real authenticated question, research progress, source links, reconnection behavior, uploads and a return visit to saved history.

## Static build and deployment notes

```bash
API_URL=/api ./scripts/build-s3-site.sh
```

This writes `dist/site/`, with the public API URL in its generated `env.js`. For production, prefer a same-origin HTTPS `/api` proxy with cookie forwarding and no caching of authenticated responses. The static build alone is not a functional deployed app: database, API, auth cookies, SSE, reset mail and uploads also need end-to-end checks. See `docs/aws-deployment.md` for the proposed private S3/CloudFront path and open operational decisions; do not treat that plan as a provisioned environment.

## Safety

DietNerd is meant to enrich conversations with registered dietitians or other qualified clinicians. Answers may miss medication interactions or pre-existing conditions. Verify important health decisions with a professional and inspect original papers before relying on a claim.
