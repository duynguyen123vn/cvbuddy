# CVBuddy AI Contract

This document turns the product planning notes into stable contracts for the
React/React Native and Node teams.

## Ownership Boundary

The AI service owns:

- CV parsing support, text normalization, and optional PII masking.
- Prompt/rubric/taxonomy design.
- Structured JSON responses for CV scoring, translation, and portfolio copy.
- Guardrails such as no hiring guarantees and no invented experience.

The Node/backend and frontend own:

- Auth, subscriptions, quotas, uploads, Cloudinary URLs, and persistence.
- Job queues for heavy CV work.
- Rendering scores, diffs, chat UI, and history.
- Payment webhooks and human mentor workflow.

Heavy CV processing should run through a job queue. Avoid long synchronous HTTP
requests from the web app.

## Endpoints

All API routes use the canonical `/v1` prefix. In production, every `/v1/*`
request must include `X-AI-Internal-Key`; the secret is shared between the
FastAPI service and the trusted server-side caller. Do not put this key in a
browser application.

Every response includes `X-Request-ID`. AI-generated responses include a
structured `meta` object with `source`, `provider`, `model`, `schemaVersion`,
`promptVersion`, and `latencyMs`. Errors use a stable `error.code` and generic
public message; validation responses do not echo submitted values.

### `POST /v1/cv/analyze`

Input shape is represented by `AnalyzeCvRequest`.

Important fields:

- `sections`: extracted CV sections. Prefer this over sending raw files to the LLM.
- `industry_slug`: taxonomy key such as `marketing`, `language`, or `computer_science`.
- `vertical_slug`: optional sub-context such as `english_language`, `software_engineering`, or `hospitality_management`.
- `company_model`: `corporate` or `startup_agency`.
- `jd_extract`: optional structured job description data.
- `language`: `vi`, `en`, or `both`.
- `tier`: `free` or `subscription`.
- `local_metrics`: computed before the LLM call.

Output shape is `AnalyzeCvResponse`:

- `overall_score`
- `dimensions.layout_ats`
- `dimensions.language`
- `dimensions.keywords`
- `dimensions.jd_fit`
- `rewrites`
- `company_model_feedback`
- `confidence`
- `disclaimer`
- `meta.source`, `meta.provider`, `meta.model`, `meta.schemaVersion`,
  `meta.promptVersion`, and `meta.latencyMs`

### `POST /v1/translate`

Input shape is `TranslateRequest`.

- `mode=literal`: preserve meaning closely.
- `mode=cv_native`: rewrite for concise CV English with stronger action verbs.
- Backend should enforce free-tier token/request limits. The AI service only receives `tier`.

Output shape is `TranslateResponse`.

### `POST /v1/portfolio/from-image`

Input shape is `PortfolioFromImageRequest`.

- `image_url`: Cloudinary or equivalent uploaded image URL.
- `industry_slug`
- `vertical_slug`
- `optional_caption`
- `tier`

Output shape is `PortfolioSuggestResponse`:

- `activity_summary_vi`
- `activity_summary_en`
- `suggested_cv_bullet_vi`
- `suggested_cv_bullet_en`
- `action_verbs`
- `industry_keywords`
- `confidence`
- `meta`

Current implementation is conservative: if no vision-capable provider is wired,
the endpoint uses `optional_caption` as the grounded context and marks
`meta.needs_user_confirmation=true`. If no caption is provided, it returns low
confidence and asks the UI to collect more context before adding content to a CV.

## CV Pipeline

Recommended production flow:

1. Upload PDF/DOCX in backend and store the original file.
2. Extract text with local libraries.
3. Normalize repeated headers/footers and section headings.
4. Compute local metrics such as quantified bullet count.
5. Analyze with taxonomy, company model, JD extract, and structured JSON output.
6. Cache by hash of CV text, industry, company model, and JD hash.
7. Count free-tier usage in PostgreSQL. Do not trust the client for quota.

Scanned PDFs need OCR and should be handled as a separate phase/budget item.

## Prompt Assets

Prompt and taxonomy assets should stay version-controlled:

- `prompts/base/system.md`
- `prompts/company_models/corporate.md`
- `prompts/company_models/startup_agency.md`
- `prompts/industries/*.yaml`

The product difference is the context matrix:

- Layer 1: general CV rubric.
- Layer 2: industry taxonomy.
- Layer 3: company model rubric.
- Optional layer: JD and sub-vertical.

## Guardrails

- Never promise that a user will be hired.
- Do not invent work history, metrics, roles, or achievements.
- Mark rewrites with `needs_user_fact=true` when a suggested metric/fact must be verified.
- Prefer masking email and phone before provider calls when compliance requires it.
- Avoid logging full CV text in application or provider logs.
- Portfolio image output must be confirmed or edited by the user before insertion into a CV.

## Suggested MVP Phases

1. Months 1-2: taxonomy for first 5-7 industries, corporate/startup rubrics, analyze JSON prototype.
2. Months 3-4: stable PDF/DOCX extraction, analyze API, cache, and free quota integration.
3. Month 5: CV-native translation and bilingual suggestions.
4. Month 6: portfolio image/caption beta.
5. Months 7-8: interview beta, cost optimization, and golden tests.

Forum CV review is mostly social/UGC. AI should be optional there, for example
to suggest more constructive comments.
