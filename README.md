# ChronicNerd / DietNerd

ChronicNerd is a conversational diet and nutrition research app in the CustomNerd family. The current web UI and assistant are branded **DietNerd**. It helps a signed-in user explore published research, inspect linked sources, and continue questions within saved conversations. It is an exploratory tool, not a medical diagnosis or a substitute for a dietitian.

## What you can do

Ask a nutrition question and watch the research journey as the server finds and checks papers. The live tracker shows stages and retrieved paper titles, not a claim that any title proves the answer. You can open article analysis and original source links when a citation can be resolved. A saved conversation keeps its turns together so you can ask follow-ups; titles can be searched or renamed, and you can jump between previous and latest messages or browse chapters and replay the stages seen during a request.

You can dictate a question in a browser that supports speech input, then review it before sending. Answers can be copied, and conversations can be downloaded as readable PDFs. Numeric tables may be viewed as charts while the underlying table stays available; chart values can seed a follow-up question. The About page has an illustrated Features gallery, and the site has a light/dark sun-and-moon switch with reduced-motion behavior.

The diet profile is optional. A saved conversation can choose whether to use it; temporary chat does not use the saved profile, keeps only bounded turns in the current tab, and does not add those turns to history. A profile may contain an age range, goals, conditions and additional notes such as activity or measurements. Those are self-reported context, not a diagnosis or a source of research evidence. A generic cached answer must not replace personalized research.

Related saved-question suggestions, attachment research (including a selected paper), claim-source inspection and reference analysis remain available. An article title, citation match or generated claim is not independently verified support. PDF and article links should be checked against the paper when a decision matters.

### Answer depth

Each question can use **Light** (the standard PubMed and evidence flow) or **Heavy**. The supplied DietNerdV2 code's standard PubMed path overlaps the existing app; its distinct detailed path combines a PubMed search with an explicitly selected PMID or PDF and a broader synthesis. Heavy adapts that combined-source path into the current authenticated app. Selected PMIDs join the processed PubMed set, while selected PDFs are summarized separately and clearly labeled as unverified user-provided sources; they are never saved as published article analysis or promoted to Article Analysis links. Heavy does not use generic answer caching. Citation and safety rules from the current app stay in force: it never forces a minimum reference count when directly relevant human sources are lacking. It can take longer than Light.

The user's diet profile can also hold private PDF/TXT/CSV files, up to 5 MB each. The profile text and files are context only when "Use my profile" is enabled for a saved conversation. Temporary chat never reads them. Ordinary saved-chat attachments remain separate from these profile files.

Heavy source-combination behavior has local unit tests, but production deployment and a live, source-grounded answer verification are separate checks. A full review of every branch in the original DietNerdV2 code is not claimed.

## Implementation

- FastAPI research API (`dietnerd-backend/`) searches and processes literature, builds answers and streams progress over server-sent events (SSE).
- Responsive HTML, CSS and JavaScript chat (`dietnerd-website/`) with conversation history, source UI, article analysis, profile controls, and the public Features page.
- MySQL-backed accounts and saved conversations. Passwords use bcrypt; session tokens are stored as digests and sent in HttpOnly cookies. Changing a password revokes other sessions.
- Docker Compose and API/browser tests. Research checks that stub external science APIs do not prove a live PubMed or model answer.

A research request can take time. SSE can reconnect to the same running API process, but a process restart may interrupt an in-flight request. Saved turns remain in MySQL. The last eight turns help interpret follow-up intent; prior answers are not scientific evidence.

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
