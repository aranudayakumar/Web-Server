Environment variables
---------------------

Copy `.env.example` to `.env` for local development and replace placeholders. The canonical
API validates `DATABASE_URL`, a 32+ character `JWT_SECRET`, `OPENAI_API_KEY`, and
`OPENAI_MODEL` during startup. Never commit `.env`.

```shell
DATABASE_URL=sqlite:///./database.db
JWT_SECRET=replace-with-at-least-32-random-bytes
VERIFIED_USERS=farmer@example.com
OPENAI_API_KEY=replace-with-your-api-key
OPENAI_MODEL=replace-with-an-available-responses-api-model
```

Local installation
------------------

Create and activate a virtual environment, then install the declared Python
dependencies:

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Guardrails validators
---------------------

`NSFWText` and `RestrictToTopic` are distributed through Guardrails Hub rather
than as dependencies that `pip install -r requirements.txt` can install. Install
both validators into the active virtual environment:

```shell
guardrails hub install hub://guardrails/nsfw_text
guardrails hub install hub://tryolabs/restricttotopic
```

Guardrails Hub currently requires the Guardrails CLI to be configured with an
authenticated Hub account before it will install these validators. Do not store
the Guardrails token in this repository. The application remains importable
without usable optional Hub validators. Chat validation is enabled when both
validators are installed; the API remains runnable when they are unavailable.

Alembic migrations
------------------

Alembic reads `DATABASE_URL` from the centralized application settings and uses
the local SQLite default when the variable is not set:

```shell
alembic current
alembic heads
```

Start the canonical API:

```shell
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`app.main:app` is the only canonical backend entry point. Authentication is bearer JWT via
`POST /api/token`; protected application routes include `/profiles`, `/logbook`, `/chats`,
`/conversations`, `/knowledge`, `/recommendations`, and `/voice`.

Local MySQL with Docker Compose
-------------------------------

Start MySQL and the canonical FastAPI service:

```shell
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Run the MySQL authentication integration test from a local virtual environment:

```shell
MYSQL_TEST_DATABASE_URL=mysql+pymysql://ugandai:localdev@127.0.0.1:3307/ugandai \
python -m unittest -v tests.test_auth_mysql
```

The existing SQLite authentication tests remain available with:

```shell
python -m unittest -v tests.test_auth
```
# Manual knowledge ingestion (Week 4)

After applying migrations, ingest a UTF-8 source document manually:

```bash
python -m app.knowledge.ingest --file tests/fixtures/uganda_maize_public_domain.txt \
  --title "Uganda Maize Growing Notes" --source "fixture:uganda-maize-notes"
```

Embeddings use `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`). Chat retrieval
uses Python cosine similarity over JSON vectors stored in MySQL; `KNOWLEDGE_TOP_K` defaults
to 3 and `KNOWLEDGE_SIMILARITY_THRESHOLD` defaults to 0.25.

## Inspecting documents, chunks, and citations

Every retrieved chunk used to ground an answer is persisted to `citations` alongside the
assistant's message, so answers stay auditable after the fact:

- `GET /knowledge/documents` — list ingested documents
- `GET /knowledge/documents/{document_id}/chunks` — list a document's chunks
- `GET /knowledge/messages/{message_id}/citations` — the chunks/documents cited in a given
  assistant answer (scoped to the requesting user's own conversation)
- `GET /knowledge/ingestion-runs` — history of scheduled ingestion sweeps (see below)

All require the same bearer auth as `/chats`.

# Scheduled ingestion + Voice (Week 5)

## Scheduled ingestion worker

`app/knowledge/worker.py` replaces manual, one-off runs of `app.knowledge.ingest` with an
unattended sweep: it scans `KNOWLEDGE_INGESTION_DIR` (default `./knowledge_sources`) for
`.txt` files and ingests any that aren't already stored (dedup is by content checksum, same
as manual ingestion). Every run is logged to `ingestion_runs` and inspectable at
`GET /knowledge/ingestion-runs`.

Two ways to trigger it, matching how it's deployed:

- **Cron**, on any long-running host:
  ```bash
  # crontab -e
  0 * * * * cd /path/to/Web-Server && OPENAI_API_KEY=... DATABASE_URL=... \
    python -m app.knowledge.worker >> /var/log/ugandai-ingestion.log 2>&1
  ```
- **AWS Lambda + CloudWatch (EventBridge) scheduled rule**: package the `app` module as a
  Lambda deployment and set the handler to `app.knowledge.worker.lambda_handler`. Attach an
  EventBridge rule with a `rate(1 hour)` or `cron(...)` schedule expression targeting the
  function, and give the function's execution role network access to `DATABASE_URL` and the
  `OPENAI_API_KEY`/`OPENAI_EMBEDDING_MODEL` env vars it needs. This repo does not provision
  the Lambda or the EventBridge rule itself — deploy those with your existing AWS tooling.

Run it locally once with:

```bash
python -m app.knowledge.worker
```

Each source is processed in its own database savepoint. A bad source is recorded without
rolling back successful sources, and checksum deduplication makes repeated sweeps idempotent.

## Voice (STT + TTS)

`POST /voice/chat` accepts a multipart audio upload (`audio`), transcribes it with OpenAI
speech-to-text (`OPENAI_STT_MODEL`, default `whisper-1`), runs the transcript through the
same RAG chat pipeline used by `/chats` (guardrails, retrieval, citations), and synthesizes
the reply as MP3 with OpenAI text-to-speech (`OPENAI_TTS_MODEL`/`OPENAI_TTS_VOICE`, default
`gpt-4o-mini-tts`/`alloy`). The response is JSON:

```json
{
  "transcript": "When should I plant maize?",
  "content": "Plant maize after the rains begin.",
  "citations": [{"document_id": 1, "chunk_id": 4, "title": "...", "source": "...", "url": null, "chunk_index": 0, "score": 0.91}],
  "audio_base64": "...",
  "audio_format": "mp3"
}
```

### Alternate provider: Sunbird AI (Ugandan languages)

OpenAI's Whisper/TTS only handle English well. Set `VOICE_PROVIDER=sunbird` to route STT/TTS
through [Sunbird AI](https://docs.sunbird.ai/languages) instead, whose models are fine-tuned
for Luganda, Acholi, Ateso, Lugbara, Runyankole, Swahili, and dozens more African languages.
`app/voice/router.py`'s `get_speech_to_text()`/`get_text_to_speech()` pick the provider at
request time based on this setting — `app/voice/sunbird_stt.py` and `sunbird_tts.py` match
the same `transcribe()`/`synthesize()` interface as the OpenAI classes, so nothing else in
the voice pipeline changes.

Config (`SUNBIRD_API_TOKEN` is required when `VOICE_PROVIDER=sunbird`):

| Variable | Default | Notes |
|---|---|---|
| `SUNBIRD_API_BASE_URL` | `https://api.sunbird.ai` | |
| `SUNBIRD_API_TOKEN` | — | Bearer token from Sunbird's `/auth/token` (currently ~7-day validity — rotate it) |
| `SUNBIRD_STT_LANGUAGE` | `lug` | ISO 639-3 code passed to `/tasks/audio/transcriptions` |
| `SUNBIRD_TTS_LANGUAGE` | `lug` | Passed to `/tasks/audio/speech` |
| `SUNBIRD_TTS_VOICE` | (unset) | Speaker/voice catalog ID (e.g. `salt_lug_0001`); left unset, Sunbird auto-resolves a voice for the language |
| `SUNBIRD_TIMEOUT_SECONDS` | `30` | |

Sunbird's TTS endpoint returns a JSON body with an `audio_url` rather than raw bytes;
`SunbirdTextToSpeech.synthesize()` fetches that URL and reads the actual returned format off
its `Content-Type` header (exposed afterward as `.audio_format`) rather than assuming MP3.

## Verification and rollback

Run the full local suite with `python -m unittest discover -s tests -v`. For MySQL, set
`MYSQL_TEST_DATABASE_URL` as shown above, run `alembic upgrade head`, then `alembic check`.
Android uses `./gradlew testDebugUnitTest assembleDebug lintDebug`.

For a bad local release, stop the API, check out the previously verified Git commit, and run
`alembic downgrade <previous_revision>` only against a disposable/local database after
reviewing the migration. For a deployed release, restore the application version first and
follow the environment's reviewed database-backup procedure; never improvise a production
downgrade or destructive reset.
