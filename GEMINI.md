# AGENTS.md: Memory Fabric (read this at the start of EVERY session)

## 1. What you are building
A **shared memory and coordination layer for multiple AI agents**, built on FalkorDB, exposed to agents through MCP. A small support-desk "crew" (Triage, Billing, Tech agents) serves customers across sessions. Memory persists, updates over time, and is available to every agent that needs it:
- **Episodic memory:** what happened in past sessions (Episode nodes).
- **Semantic memory:** what is true about a user, with history (Fact nodes linked by SUPERSEDES).
- **Procedural memory:** how to solve problems, learned from outcomes and promoted when proven (Procedure nodes).
- **Persistent conversation history** (Session, Message nodes), **handoffs** with context bundles, shared state, task claiming, and **one graph per tenant** for isolation.
A React UI shows the memory graph, the crew working, and live proof of isolation and concurrency.
Hackathon: Graph Hacks (Oct 15 to 18, 2026 IST). Track: *Agent Memory and Coordination*. FalkorDB must be central: the product must not work without it.

## 2. How to work (the loop)
1. Open `TASKS.md`. Find the **next unfinished task** (T0, T1, T2, ...).
2. Read this file, then **only** the files named in that task's `Read first:` line.
3. Do **only that task**. Do not start the next one.
4. Run every command in the task's **Acceptance** block. All must pass.
5. Paste the real command output into `BUILD_LOG.md` under the task heading.
6. Commit and push following `docs/spec/07-git-commits.md` (summary in Section 6 below).
7. Mark the task done in `BUILD_LOG.md`. Stop, or continue with the next task.

## 3. Hard rules (DO / DO NOT)
DO:
- Copy numbers, ids and text from `docs/spec/01-data.md`. If you need a number, open the file. Do not recall it from memory.
- Put **all Cypher** in `memory_core/queries.py` (exceptions: `scripts/probe_falkordb.py`, `seed/seed.py`, `schema.py` for index/constraint statements).
- Get the tenant, user, agent and session **only from the bound context** (Section 7). Never read them from LLM output.
- Validate `tenant_id` with the regex before any DB call. Interpolate only validated ints or whitelisted labels into Cypher; pass everything else as parameters.
- Use the injectable clock (`memory_core/clock.py`). Never call `time.time()` or `datetime.now()` elsewhere.
- Use type hints and a one-line docstring on every public function. Keep files small.
- Write a test for every function that has logic.
- Log every deviation or decision in `DECISIONS.md` as one line: `date | decision | reason`.
- Use synthetic data only. Disclose AI assistance in the README (task T18). Keep `.env` out of git. Never print secrets.

DO NOT:
- Add a library that is not in `docs/spec/00-stack.md`.
- Add features outside Section 5 (Scope) below.
- Run any query that touches more than one tenant graph (the isolation checks in `isolation-check` are the only code that may open a second tenant, and only to prove denial).
- Change a golden value to make a test pass. If a test disagrees with `01-data.md`, first re-check your seed transcription and the tokenizer. If the spec arithmetic is truly wrong, log it in `DECISIONS.md` and tell the owner.
- Print "tests passed" without running them. Never invent command output.
- Backdate commits, rewrite pushed history, or force-push.
- Skip a failing acceptance check and move on.
- Import `google.genai` or `anthropic` anywhere except `backend/llm/` and (for embeddings) `memory_core/embedder.py`.
- Return `embedding` vectors through any API, tool or event.

## 4. Stack (summary; full list in `docs/spec/00-stack.md`)
| Layer | Choice |
|---|---|
| Database | FalkorDB (Docker, pinned tag), **one graph per tenant** `mem_<tenant>`, client `falkordb` (async if the probe allows) |
| Vector search | FalkorDB vector index (cosine); embeddings: deterministic mock (default) or Gemini `gemini-embedding-001` |
| MCP | `mcp` Python SDK, `FastMCP`, stdio |
| Backend | Python 3.11+, FastAPI, uvicorn, sse-starlette, Pydantic v2 |
| LLM | **Gemini `gemini-3.8-flash`** via `google-genai`, behind the `LLMSession` interface (`docs/spec/04-agent-llm-api.md`) |
| Keyless mode | `AGENT_MODE=mock` scripted agents (default for tests and CI) |
| Frontend | Vite + React 18 + TypeScript, Tailwind, shadcn/ui, `@xyflow/react`, `@dagrejs/dagre` |
| Tests | pytest (+ asyncio, httpx), vitest |

## 5. Scope
IN: tenants `acme` and `globex`; nodes User, Agent, Entity, Session, Message, Episode, Fact, Procedure, Task, Handoff, StateEntry; three agent scenarios (`continuity`, `fact_update`, `procedure_learning`); isolation and load-test scenarios; replay mode; evals; README and docs.
OUT: agent-private scratchpads, per-message embeddings, real email/Slack, login/OAuth (API keys only), more than two seeded tenants, extra databases, LLM-based fact extraction (extraction is rule-based).

## 6. Git rules (summary; full plan in `docs/spec/07-git-commits.md`)
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:` + optional scope.
- One logical change per commit. Tests pass before every commit. Read `git diff --staged` before committing.
- Push to `origin main` after every task.
- Tags: `v0.1-core`, `v0.2-memory`, `v0.3-agents`, `v0.4-ui`, `v1.0`.
- If you cannot push, commit locally and tell the owner the exact commands to run.

## 7. Conventions
- **Context fields** `tenant_id`, `user_id`, `agent_id`, `session_id` are injected by the runtime. The LLM never sees or sets them.
- Tenant graph name: `mem_<tenant_id>`; `tenant_id` regex `^[a-z][a-z0-9_]{2,31}$`.
- Edge key: `<src_id>|<REL_TYPE>|<dst_id>`.
- Timestamps: integer epoch seconds (tasks: epoch milliseconds); ISO strings only at the API boundary.
- Error codes: `NOT_FOUND`, `INVALID_INPUT`, `FORBIDDEN`, `CONFLICT`, `DB_ERROR` (class `MemoryError` subclasses in `memory_core/errors.py`).
- Conditional writes: the check and the write happen in **one** Cypher statement; zero returned rows means the condition failed.

## 8. Repository layout (create exactly)
```
README.md DECISIONS.md BUILD_LOG.md AI_DISCLOSURE.md Makefile docker-compose.yml .env.example requirements.txt pyproject.toml
AGENTS.md GEMINI.md TASKS.md docs/spec/*.md
scripts/{probe_falkordb, probe_gemini, run_scenario, load_test}.py
seed/{seed.py, data/acme.json, data/globex.json}
memory_core/{__init__,config,clock,errors,tenancy,db,embedder,schema,queries,history,semantic,recall,consolidation,procedural,coordination,loadtest}.py
memory_mcp/{__init__,server,context,allowlist,envelope,models}.py
backend/{__init__,main,auth,events,mcp_bridge,agent_live,agent_mock,scenarios,crew,prompts}.py
backend/llm/{__init__,base,schema,gemini_client,anthropic_client,fake_client}.py
tests/{test_tenancy,test_embedder,test_seed,test_history,test_semantic,test_recall,test_consolidation,test_procedural,test_coordination,test_mcp_tools,test_schema_simple,test_isolation,test_llm_gemini,test_agent_mock,test_agent_live,test_api,test_load_small}.py
evals/{scenarios.yaml, run_evals.py, ablation.py, results.md, load_results.md}
frontend/          (Vite app)
docs/{queries.md, architecture.md, EXPLAINER.md, OWNER_QUESTIONS.md, demo_script.md}
replays/{continuity, fact_update, procedure_learning}.jsonl
```
`Makefile` targets that must work: `make up`, `make seed`, `make probe`, `make test`, `make dev` (backend :8000), `make web` (frontend :5173), `make eval`, `make load`, `make reset`.

## 9. Environment variables (`.env.example`)
See `docs/spec/00-stack.md` Section 0.1 for the full list and defaults. Never commit a real key.

## 10. Index: where each part of the spec lives
| Section | Topic | File |
|---|---|---|
| 0 | Fixed decisions, library manifest | `docs/spec/00-stack.md` |
| 1, 2, 3 | Conventions and graph model, seed data, golden values G1 to G15 | `docs/spec/01-data.md` |
| 4, 5, 6 | Cypher queries, retrieval and update rules, coordination protocols, fallbacks | `docs/spec/02-memory-queries-rules.md` |
| 7 | MCP tools, context fields, role allowlists | `docs/spec/03-mcp-tools.md` |
| 8 | Context injection, LLM adapter (Gemini), turn loop, crew runner, mock scenarios, prompts, REST API, SSE events | `docs/spec/04-agent-llm-api.md` |
| 9 | Frontend | `docs/spec/05-frontend.md` |
| 10, 11 | Load test, evals, README requirements, demo script | `docs/spec/06-load-evals-docs.md` |
| 12 | Git workflow and commit plan | `docs/spec/07-git-commits.md` |
| tasks, Definition of Done | Ordered task list | `TASKS.md` |

## 11. If you are stuck
1. Re-read the task's `Read first:` files.
2. Run the failing command again and read the full error.
3. Check `DECISIONS.md` for a related decision (especially the probe results).
4. If a FalkorDB feature behaves differently than the spec says, use the matching fallback in `docs/spec/02-memory-queries-rules.md` Section 6.5 and log it.
5. If blocked by something outside the repo (no API key, no Docker, no git remote), write the blocker in `BUILD_LOG.md`, finish everything that does not depend on it, and tell the owner.
