# Spec 00: Stack (fixed decisions and library manifest)

- **Purpose:** Lists every technology decision. There are no open choices.
- **Read this when:** starting T0, adding any dependency, or unsure which library to use.

---

## 0.1 Fixed decisions

| Area | Decision |
|---|---|
| Python | 3.11+; `pip` + `requirements.txt` |
| DB | FalkorDB Docker image **pinned to a specific tag** (record the exact tag in `DECISIONS.md`; never `latest`) |
| Tenancy | **One FalkorDB graph per tenant**, named `mem_<tenant_id>` (for example `mem_acme`). `tenant_id` must match `^[a-z][a-z0-9_]{2,31}$` |
| DB client | `falkordb` Python package. Use the async client (`falkordb.asyncio`) if probe F1 passes; otherwise the sync client wrapped in `asyncio.to_thread` with a bounded `ThreadPoolExecutor(max_workers=32)`. Connection pool max 64 |
| Reads / writes | Read tools use `ro_query`; write tools use `query` |
| Embeddings | `EMBED_PROVIDER=mock` (default; deterministic hashing embedder, dimension 4096) or `gemini` (model `gemini-embedding-001`, dimension 768, requested via `output_dimensionality`; verify in the Gemini probe). Always L2-normalize |
| Vector search | FalkorDB vector index (HNSW, cosine) on `Episode.embedding`, `Fact.embedding`, `Procedure.embedding`. Dimension must be a literal inside `CREATE VECTOR INDEX`; build the statement after validating `EMBED_DIM` as an int |
| Important limit | **Vector index queries do not combine with property filters.** Always fetch `k * 5` candidates from the index, then filter with `MATCH`/`WHERE` after `YIELD` (Section 4) |
| MCP | `mcp` Python SDK, `FastMCP`, stdio transport |
| Backend | FastAPI + uvicorn, SSE via `sse-starlette`, Pydantic v2 |
| LLM | **Gemini `gemini-3.8-flash`** via `google-genai`, behind the `LLMSession` interface (Section 8.2). Thinking level env `GEMINI_THINKING_LEVEL` (`low`, `medium` default, `high`; `minimal` is NOT supported) |
| Keyless mode | `AGENT_MODE=mock` runs **scripted agents** (Section 8.5) with identical event output. Default in tests and CI |
| Clock | All code gets time from `memory_core/clock.py: now()`; env `CLOCK_NOW` (ISO UTC) freezes it. Tests and golden values use `2026-10-16T00:00:00Z` |
| Timestamps | Stored as integer **epoch seconds** (`ts`, `started_at`, `valid_from`, ...). Task `created_at` uses epoch **milliseconds**. API responses convert to ISO-8601 |
| Tests | `pytest`, `pytest-asyncio` |
| Frontend | Vite + React 18 + TypeScript, Tailwind, shadcn/ui, `@xyflow/react`, `@dagrejs/dagre` |

**Env vars** (`.env.example`): `FALKORDB_HOST=localhost`, `FALKORDB_PORT=6379`, `TENANTS=acme,globex`, `TENANT_KEYS=acme:acme-demo-key,globex:globex-demo-key`, `AGENT_MODE=mock`, `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=`, `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_THINKING_LEVEL=medium`, `EMBED_PROVIDER=mock`, `EMBED_DIM=4096`, `EMBED_MODEL=gemini-embedding-001`, `CLOCK_NOW=` (empty = real time), `MAX_INFLIGHT=64`.

If you switch `EMBED_PROVIDER` or `EMBED_DIM`, you must **reset and re-seed** (vector index dimension changes).

## 0.2 Library manifest (install exactly these; add nothing else without logging it in `DECISIONS.md`)

**Backend (`requirements.txt`)**

| Purpose | Package |
|---|---|
| API server | `fastapi`, `uvicorn[standard]` |
| SSE | `sse-starlette` |
| Validation, settings | `pydantic>=2`, `pydantic-settings` |
| MCP | `mcp` |
| LLM and embeddings | `google-genai` |
| Graph DB client | `falkordb` |
| Tests | `pytest`, `pytest-asyncio`, `httpx` |
| Config / evals | `pyyaml` |
| Lint | `ruff` |

Cosine similarity and tokenizing are written in pure Python (no numpy). After installing, pin exact versions (`pip freeze` filtered) and commit.

**Frontend (`frontend/package.json`)**: `vite`, `react@18`, `react-dom@18`, `typescript`, `tailwindcss` (+ `postcss`, `autoprefixer`), shadcn/ui (only `button`, `card`, `badge`, `scroll-area`, `tabs`, `input`), `lucide-react`, `@xyflow/react`, `@dagrejs/dagre`, `vitest`. State: `useReducer` only. Streaming: native `EventSource`. HTTP: native `fetch`. Commit `package-lock.json`.

**Explicitly NOT used:** LangChain, LangGraph, LlamaIndex, any vector DB other than FalkorDB, Redis clients for app logic (except as a fallback in Section 6.5), SQLAlchemy, Celery, Redux, Zustand, React Query, axios, numpy.

**Tooling:** Docker Compose, `Makefile`, `.github/workflows/ci.yml` running `pytest` (mock mode, FalkorDB service container) plus `npm run build`, `npx tsc --noEmit`, `npx vitest run`.
