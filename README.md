# DietNerd

## About ChronicNerd

ChronicNerd is the conversational DietNerd project: a research assistant for evidence-based diet and nutrition questions, with durable user conversations, rolling summaries, follow-up question rewriting, and document uploads. It is part of the CustomNerd research family and is developed by:

- **Sanghita Chakraborty** - New York University, New York, USA
- **Harsh Kashyap** - Thapar Institute of Engineering and Technology, Patiala, India
- **Dennis Shasha** - Department of Computer Science, New York University, New York, USA

![DietNerd Logo](dietnerd-website/assets/dietnerd_logo.png)

DietNerd (https://dietnerd.org/) is a web-based LLM-powered tool that answers diet and nutrition-related questions by extracting and summarizing information from academic papers sourced from PubMed. Users can ask questions on various topics, including dietary strategies, nutrition science, and health outcomes, and receive detailed, evidence-based responses based on the latest research. It utilizes a unique article search strategy and is built with multiple safety-motivated touchpoints, including a safety analysis that evaluates the pros, cons, and risks of the topics in question.

The tool is designed to provide reliable and up-to-date information for individuals, health professionals, and researchers alike. Our mission is to enrich conversations between patients and their medical providers and equip users with knowledge.

## Features

- Query-based diet and nutrition information
- Evidence-based answers backed by scientific research
- Similar question suggestions
- PDF generation of answers
- Reference analysis with links to full articles

## Technology Stack

- Frontend: HTML, CSS, JavaScript
- Backend API
## Project Structure

- `index.html`: Main page of the application
- `index.js`: Core functionality for querying and displaying answers
- `index.css`: Styles for the main page
- `reference.html`: Page for displaying detailed reference information
- `reference.js`: Functionality for the reference page
- `reference.css`: Styles for the reference page
- `about.html`: Information about DietNerd and the team
- `about.css`: Styles for the about page
- `contact.html`: Contact form for user feedback
- `contact.css`: Styles for the contact page
- `env.js`: Environment variables for API endpoints and email service

## Team

- Professor Dennis Shasha @ New York University
- Shela Wu @ New York University
- Zubair Yacub @ University of Illinois Urbana Champaign

## Disclaimer

DietNerd is an exploratory tool designed to enrich conversations with registered dietitians or registered dietitian nutritionists. The insights provided may not fully consider all potential medication interactions or pre-existing conditions. Always consult with a healthcare professional for personalized advice.


## Accounts and sign-in

Every API route needs a signed-in user. Passwords are hashed with bcrypt and the
session lives in an HttpOnly cookie (`dietnerd_session`) backed by a server-side
sessions table, so signing out or changing the password revokes it.

- `POST /register`, `POST /login`, `POST /logout`, `GET /me`
- `POST /forgot_password` always answers the same way, so it never reveals whether an account exists. The emailed link opens `login.html#reset_token=...` and expires after `RESET_TTL_MINUTES` (default 30).
- `POST /reset_password` sets a new password and signs out every other session.
- `POST /change_password` needs the current password.
- Login, register and forgot-password are rate limited per client.

Reset mail goes out through Amazon SES when `MAIL_FROM` (a verified SES identity) and `AWS_SES_REGION` are set, through SMTP when `SMTP_HOST` is set, and otherwise the link is only written to the API log. `MAIL_BACKEND=ses|smtp|log` forces one. See `.env.example`.

## Run locally with Docker

```bash
cp .env.example .env      # add OPENAI_API_KEY, NCBI_API_KEY and the publisher keys
docker compose up --build
```

- Site: http://localhost:8080
- API health check: http://localhost:8000/health

The compose file starts MySQL 8, the API (tables are created on startup) and an nginx container serving `dietnerd-website/`. `dietnerd-website/env.js` points the site at `http://localhost:8000`; change `API_URL` there, and `ALLOWED_ORIGINS` / `PUBLIC_SITE_URL` in `.env`, when the site moves to a real domain. Set `COOKIE_SECURE=1` once it is served over HTTPS.

## Clean local verification

The API tests use MySQL-specific transactions, foreign keys, and locking, so they should not be replaced with SQLite. A disposable MySQL 8 fixture is provided for a clean-clone run:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
./tests/run_local_mysql_tests.sh
```

The script starts an isolated MySQL container, runs the API and concurrency integration tests plus the remaining test suite, and removes the database container and volume on exit. It uses port `33306` by default; set `CHRONICNERD_TEST_MYSQL_PORT` if that port is occupied.

For the browser fixture after the MySQL tests are green:

```bash
npm ci
# With the same DB environment variables (host, port, user, password, database):
./tests/run_browser_e2e.sh
node tests/browser_xss_e2e.js
```

`run_browser_e2e.sh` starts the stubbed API and the static site, then drives real Chrome through register, a cached answer, a follow-up that uses conversation memory, a new conversation, a file upload, delete, sign out, forgot password, the reset link, and signing in with the new password. Screenshots are written to `/downloads/`.

The browser fixture stubs only the external science APIs. A release claim still requires a separate live OpenAI/PubMed pass with valid credentials.
