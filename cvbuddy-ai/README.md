# CVBuddy AI Service

FastAPI service for lossless CV extraction, structured analysis, translation, and portfolio suggestions. PDF/DOCX processing runs locally and LLM inference uses Groq Cloud.

## Runtime

- Python 3.12
- FastAPI and Pydantic v2
- PyMuPDF/python-docx for document extraction
- Groq with Qwen 3.8 27B as the primary extraction/analysis model and GPT OSS 120B as fallback

## Start

Prerequisites:

1. Create a free Groq API key.
2. Copy `.env.example` to `.env`.
3. Set `GROQ_API_KEY` in the backend `.env`.

```powershell
cd E:\Project\cvbuddy-ai
.venv-codex\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8001
```

- API docs: http://localhost:8001/docs
- Liveness: http://localhost:8001/health
- Readiness: http://localhost:8001/ready

The sample frontend in `E:\Project\cvbuddy-web` is configured to use port `8001`.

## Configuration

Default Groq setup:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_EXTRACT_MODEL=qwen/qwen3.8-27b
GROQ_ANALYZE_MODEL=qwen/qwen3.8-27b
GROQ_FALLBACK_MODEL=openai/gpt-oss-120b
MOCK_LLM=false
APP_ENV=development
APP_VERSION=0.1.0
APP_COMMIT=local
API_PREFIX=/v1
AI_RATE_LIMIT_PER_MINUTE=60
AI_INTERNAL_API_KEY=
AI_SCHEMA_VERSION=ai-response-v1
AI_PROMPT_VERSION=cv-prompts-v1
```

In production, set every variable above explicitly in the FastAPI secret/config store.
Set `APP_COMMIT` to the deployed Git SHA. Do not copy the internal key or Groq key
to a browser bundle, Git, logs, or chat. `/ready` returns 200 only when the
production provider, keys, model IDs, schema/prompt versions, and mock mode pass
validation. `/health` is liveness-only and never calls Groq.
The API also applies a per-internal-key, per-process limit (default 60 requests
per minute). Use a shared gateway/Redis limiter before scaling to multiple
workers or instances.

## CV Flow

```text
PDF/DOCX
  -> PyMuPDF/python-docx text blocks
  -> Groq Qwen 3.8 27B section parsing when mode=ai
  -> structured_document + coverage audit
  -> industry validation
  -> Groq Qwen 3.8 27B analysis, with GPT OSS 120B fallback
  -> grounded JSON response
```

Extraction modes:

- `local`: deterministic section rules only.
- `hybrid`: local rules with AI parsing for weak/multi-column results.
- `ai`: always use Groq Qwen for section parsing.

The web UI uses `POST /v1/cv/extract` followed by `POST /v1/cv/analyze`.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Service health |
| GET | `/ready` | Safe config readiness |
| GET | `/v1/models` | Provider and installed model catalog |
| GET | `/v1/industries` | Industry/vertical catalog |
| POST | `/v1/cv/extract` | Extract sections, source blocks, and coverage |
| POST | `/v1/cv/analyze` | Analyze extracted sections |
| POST | `/v1/cv/extract-and-analyze` | Combined convenience endpoint |
| POST | `/v1/translate` | CV-oriented translation |
| POST | `/v1/portfolio/suggest` | Portfolio/CV bullet suggestions |

See [docs/AI_CONTRACT.md](docs/AI_CONTRACT.md) for integration contracts.

## Tests

```powershell
.venv-codex\Scripts\python.exe -m pytest
```

Tests force mock mode and never call Groq.

## Docker

The compose service exposes the API at port `8001` and reads Groq configuration from `.env`.

```powershell
docker compose up --build
```
