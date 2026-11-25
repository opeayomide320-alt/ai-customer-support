# AI Customer Support

A Gmail-based customer support assistant with a FastAPI backend, a PostgreSQL knowledge base, and a React dashboard. It classifies customer emails, retrieves relevant support information, and either sends a reply or acknowledges the message and flags the conversation for a human.

The included prompts and policies are tailored to **Harbor & Pine**, a home and outdoor store selling paddle boards and shelving on Amazon. This is a store-specific implementation: adapting it to another business requires updating the prompts, product rules, knowledge base, and dashboard branding.

For example, when a customer reports a slow leak in a paddle board and hasn’t checked the valve, the Python rules select `valve-check` as the next troubleshooting step.

## What it does

- Reads Gmail inbox messages that do not have the `ai-processed` label, up to 10 per poll. This includes existing inbox mail, not just unread or newly received messages.
- Skips messages sent by the connected account and messages marked as automated, bulk, or mailing-list mail.
- Classifies the latest customer message using the email thread for context.
- Uses a Pydantic AI agent to retrieve knowledge-base sections from PostgreSQL and compose a plain-text answer in the customer's language.
- Applies product rules to request missing details, suggest troubleshooting, or propose an action for a human colleague.
- Stores processing events, tickets, incoming messages, and sent replies in PostgreSQL.
- Provides a dashboard for viewing events and ticket conversations, editing existing knowledge-base entries, and triggering an inbox check.

**Inbox processing sends real email automatically.** There is no draft approval step or dry-run setting. Use a dedicated test mailbox before connecting a live support inbox. The dashboard's **Check inbox now** button also runs the sending pipeline.

## How a message is handled

1. The poller finds eligible Gmail messages and claims each message in the events table.
2. The pipeline checks message headers, records the incoming message, and loads the thread.
3. The classifier selects a support category and identifies cases requiring human attention.
4. For eligible questions, the reply agent reads the relevant knowledge-base sections. Decision logic checks the model's structured output and applies product-specific rules.
5. The pipeline sends either the answer or a handoff acknowledgement, records the result, and adds `ai-processed`.

Attachments, refund requests, safety concerns, requests for a person, specific order-status questions, and unsupported topics are among the escalation cases. Attachments are flagged for a human; their contents are not analyzed. Classification and extracted issue details depend on model output.

Escalation adds `needs-human` to the message and marks the ticket as escalated. Further messages in that thread are skipped while any message in the thread carries that label. A colleague handles the conversation in Gmail and removes the label from the thread's messages when automation should resume. The dashboard does not send human replies or resolve tickets.

Proposed refunds, shipments, exchanges, and replacements are recorded for a colleague; the application does not execute them or integrate with Amazon order management.

## Requirements

- Python 3.13 or newer and [uv](https://docs.astral.sh/uv/).
- Node.js 22.12 or newer and npm for the dashboard.
- PostgreSQL, either standalone or hosted by Supabase.
- A Google Cloud project with the Gmail API enabled and a Gmail account to authorize.
- An OpenAI API key with access to the configured models.

Run the commands below from the repository root unless stated otherwise.

## Setup

### 1. Install dependencies and configure the environment

```sh
uv sync --locked
npm --prefix dashboard ci
```

For a fresh setup, create `.env` from [.env.example](.env.example). These commands preserve an existing `.env` and its credentials. In PowerShell:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

On macOS or Linux:

```sh
if [ ! -e .env ]; then cp .env.example .env; fi
```

Fill in the local file using your own values:

| Variable | Purpose |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID. |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret. |
| `GOOGLE_REFRESH_TOKEN` | Refresh token for the support mailbox. |
| `DATABASE_URL` | PostgreSQL connection string, including the database credentials and any required SSL options. |
| `OPENAI_API_KEY` | API key used by the classifier and reply agent. |
| `CLASSIFIER_MODEL` | Classification model; the example uses `openai:gpt-4.1-mini`. |
| `AGENT_MODEL` | Reply model; the example uses `openai:gpt-4.1`. |
| `POLL_INTERVAL_SECONDS` | Delay between polling passes; the example sets `30`. The code defaults to `60` if omitted. |
| `DASHBOARD_USERNAME` | Dashboard login name; defaults to `admin`. |
| `DASHBOARD_PASSWORD` | Set a nonempty password. An empty value prevents login. |
| `PYDANTIC_AI_NO_BANNER` | The example sets `1` to suppress the Pydantic AI banner. |

Keep `.env` and `credentials.json` private. Both are excluded by [.gitignore](.gitignore) and [.dockerignore](.dockerignore). Share only [.env.example](.env.example), with its credential fields left empty.

### 2. Authorize Gmail

1. Enable the Gmail API in your Google Cloud project and configure its OAuth consent screen. Add your mailbox as a test user if the OAuth app is in testing mode.
2. Create an OAuth client of type **Desktop app**. Download its client configuration and save it locally as `credentials.json` in the repository root.
3. Run the authorization helper:

   ```sh
   uv run python scripts/get_refresh_token.py
   ```

4. Complete the browser consent flow for the intended mailbox, then copy the three printed `GOOGLE_*` values into your local `.env` file.

The helper requests the `gmail.modify` scope, which allows reading mail, managing labels, and sending replies. Its terminal output contains secrets; do not paste that output into issues, screenshots, or commits.

### 3. Create the database tables

Apply [the initial SQL migration](supabase/migrations/20261123182624_create_tables.sql) once to a fresh database using your PostgreSQL client or the Supabase SQL Editor. It creates `events`, `tickets`, `messages`, and `knowledge_base`.

Set `DATABASE_URL` to a connection string for that database. The backend connects directly with Psycopg; it does not use Supabase's REST API. The migration enables row-level security without adding policies, so the backend database role must have appropriate access, such as the table-owning role used for setup.

Seed the support content:

```sh
uv run python -m scripts.seed_knowledge_base
```

The seed script reads [knowledge_base/](knowledge_base/), creating one entry per `##` heading. It updates entries matching the same section and title. Re-running it can overwrite dashboard edits to those entries; it does not remove obsolete database entries. The running agent reads the database, so editing a Markdown file alone does not change its answers.

### 4. Start the API and dashboard

Start the backend in one terminal:

```sh
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the dashboard in another:

```sh
npm --prefix dashboard run dev
```

Open the URL printed by Vite, normally <http://localhost:5173>, and log in with the configured dashboard credentials. Vite proxies `/api` requests to the backend on port 8000.

The API alone does not start background polling. Once the mailbox and policies are ready, start the worker in a third terminal:

```sh
uv run python -m app.poller
```

Alternatively, use **Check inbox now** in the dashboard for a single processing pass.

## Built dashboard and containers

To build the dashboard locally:

```sh
npm --prefix dashboard run build
```

Restart the API after building. When the built dashboard directory exists, FastAPI serves it at `/` on the API's port.

[Dockerfile](Dockerfile) builds the dashboard and packages it with the Python backend. [docker-compose.yml](docker-compose.yml) defines separate `api` and `poller` services using the same image and local environment file. The API is bound to <http://127.0.0.1:8080>; the poller starts processing mail when its service starts.

The Compose setup does not provision PostgreSQL, apply migrations, or seed the knowledge base. Complete those steps first and use a database address reachable from the containers.

## Verified locally

- All 18 sample emails passed the evaluation checks for the selected knowledge-base section and the decision to reply or escalate.
- The dashboard production build succeeded. FastAPI served it on port 8000, where I viewed processing events, opened a ticket conversation, and read a knowledge-base entry.

The Docker image build and VPS deployment are pending.

## Evaluation and development

Run the model-backed evaluation dataset after configuring the environment and seeding the database:

```sh
uv run python -m evals.run_evals
```

The evaluations compare the selected section and reply/escalation action against [golden email cases](evals/golden_emails.py). They call the real models and may incur API costs, but do not send Gmail messages. They do not test the full inbox pipeline or guarantee reply quality.

For a single sample decision without sending email:

```sh
uv run python playground/try_pipeline.py
```

Dashboard checks:

```sh
npm --prefix dashboard run lint
npm --prefix dashboard run build
```

The separate [Gmail check helper](scripts/gmail_check.py) **does send a real acknowledgement** to the first eligible inbox message. It is not a read-only connectivity check and requires an eligible message to exist.

## API and operational notes

With the local API running, open the [interactive API documentation](http://127.0.0.1:8000/docs) to explore the routes. All `/api` routes require your dashboard username and password. The dashboard’s **Check inbox now** button calls `POST /api/poll`, which can send real replies.

`GET /health` is unauthenticated and returns a static status; it does not verify database, Gmail, or OpenAI connectivity.

Use HTTPS if exposing the dashboard beyond localhost. The frontend keeps the Basic authentication value in browser session storage. Email thread text is sent to the configured models, and customer addresses and message bodies are stored in PostgreSQL.

Failed messages are retried on later polls, with the pipeline adding `ai-processed` after the third failed attempt. Gmail sends and database writes are separate operations: retries after a partial failure can duplicate a reply, and interrupted events can remain in `processing`. Inspect event records when recovering from failures; this is not an exactly-once delivery system.

## Repository guide

| Location | Contents |
| --- | --- |
| [app/](app/) | FastAPI routes, Gmail integration, polling, message processing, and database access. |
| [app/ai/](app/ai/) | Classifier, reply agent, structured schemas, and product decision rules. |
| [dashboard/](dashboard/) | React, TypeScript, Vite, and Tailwind dashboard. |
| [knowledge_base/](knowledge_base/) | Product information, support policies, tone, and escalation rules used for seeding. |
| [supabase/migrations/](supabase/migrations/) | PostgreSQL schema migration. |
| [scripts/](scripts/) | OAuth setup, knowledge-base seeding, and Gmail check helpers. |
| [evals/](evals/) | Model-backed evaluation runner and example emails. |
| [playground/](playground/) | Standalone sample decision script. |
