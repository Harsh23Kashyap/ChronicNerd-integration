# DietNerd database schema

The backend uses the MySQL database configured by its environment variables.
Fresh databases are initialized on application startup. Existing deployments must back up the database and apply
`migrations/001_conversation_lifecycle.sql`. The migration preserves each
user's old email-scoped history as one "Imported legacy history" conversation
and retains the old summary table as a backup for verification.

## `users`

| Column | Type | Notes |
|---|---|---|
| `email` | VARCHAR(255) | Primary key |
| `password` | VARCHAR(255) | Legacy SHA-256 hash; P1 will replace this with a salted password hash |
| `created_at` | TIMESTAMP | Creation time |

`users` is created before every table that references it.

## `conversations`

| Column | Type | Notes |
|---|---|---|
| `conversation_id` | VARCHAR(36) | UUID primary key |
| `email` | VARCHAR(255) | Owner, FK to `users.email` |
| `title` | VARCHAR(255) | Initial question, truncated to 120 characters |
| `next_query_number` | INT | Next turn number, allocated under a row lock |
| `title_locked` | TINYINT(1) | User rename prevents automatic title updates |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last turn/update time |

## `user_session_memory`

One row per question/answer turn.

| Column | Type | Notes |
|---|---|---|
| `id` | INT | Auto-increment primary key |
| `email` | VARCHAR(255) | FK to `users.email` |
| `conversation_id` | VARCHAR(36) | FK to `conversations.conversation_id` |
| `query_number` | INT | Monotonic within a conversation |
| `request_id` | VARCHAR(36) | Ephemeral request/SSE correlation UUID |
| `raw_question` | TEXT | User input |
| `standalone_question` | TEXT | Context-rewritten input, generated once |
| `answer` | LONGTEXT | Generated or cached answer |
| `created_at` | TIMESTAMP | Turn creation time |

`(conversation_id, query_number)` is unique. Allocation locks the owning
conversation row, updates `next_query_number`, and inserts the turn in one
transaction.

## `user_conversation_summary`

| Column | Type | Notes |
|---|---|---|
| `email` | VARCHAR(255) | FK to `users.email` |
| `conversation_id` | VARCHAR(36) | FK to `conversations.conversation_id` |
| `summary` | LONGTEXT | Rolling summary for this conversation only |
| `updated_at` | TIMESTAMP | Last update |

The composite primary key is `(email, conversation_id)`.

## `user_documents`

Unchanged: extracted attachment text is stored by user and filename. The
unique key `(email, filename)` makes re-upload replace the prior content.

## Identifier lifecycle

- `conversation_id` is durable and stored by the browser across turns.
- `request_id` exists only to correlate one `/process_query` call with `/sse`.
- `query_number` is durable ordering within one conversation.

## Conversation APIs

| Endpoint | Method | Purpose |
|---|---|---|
| `/conversations` | POST | Create a conversation |
| `/conversations` | GET | List a user's conversations |
| `/conversations/{conversation_id}` | DELETE | Delete an owned conversation and cascaded turns/summary |
| `/session_memory` | GET | Read one conversation |
| `/session_memory` | DELETE | Clear one conversation's turns and summary |
| `/cached_answer` | POST | Fetch and persist a cache hit in the active conversation |
| `/process_query` | POST | Start generation and return separate request and conversation IDs |
| `/sse?request_id=...` | GET | Stream one request's updates |

The P0 model still accepts caller-supplied email as identity. P1 must replace
that with authenticated server-side identity before deployment.

## `user_profiles`

One optional row per user: the self-reported diet profile used to personalize answers.

| Column | Type | Notes |
|---|---|---|
| `email` | VARCHAR(255) | Primary key, FK to `users.email` |
| `age_range` | VARCHAR(40) | One of a fixed list, or empty |
| `goals` | VARCHAR(300) | Free text, or empty |
| `conditions` | VARCHAR(300) | Free text, or empty |
| `updated_at` | TIMESTAMP | Last save |

All three content fields empty deletes the row (Clear profile). Existing
databases apply `migrations/002_diet_profile.sql`; fresh databases create the
table at startup.

| Endpoint | Method | Purpose |
|---|---|---|
| `/profile` | GET | Read the caller's profile (empty strings when unset) |
| `/profile` | PUT | Save or clear the caller's profile |

Existing databases apply `migrations/003_conversation_rename.sql` before deploying the rename API. Fresh databases get `title_locked` on startup.
