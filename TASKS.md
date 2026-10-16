# TASKS.md: ordered task list and Definition of Done

**How to use:** do the first unfinished task. Read `AGENTS.md` and only that task's `Read first:` files. Run its Acceptance commands. Log real output in `BUILD_LOG.md`. Commit and push (`docs/spec/07-git-commits.md`). Then continue.

**Order:** T0 to T19. T12 live checks need a Gemini key; everything else works in mock mode.

**Checkpoint after T4 (agent trial):** if you are a smaller or faster model and T0 to T4 needed repeated corrections, tell the owner. They may switch you to a stronger model for T5 to T9 (the hardest tasks: recall, concurrency, MCP), then switch back.

---

**T0. Bootstrap.** Repo skeleton (`AGENTS.md` Section 8), `requirements.txt` (`falkordb, mcp, pydantic>=2, pydantic-settings, fastapi, uvicorn[standard], sse-starlette, google-genai, pytest, pytest-asyncio, httpx, pyyaml, ruff`), `docker-compose.yml` with a pinned FalkorDB tag and healthcheck, `Makefile`, `.env.example`, `.gitignore` (include `.env`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`, `probe_results.json`).
*Read first:* `AGENTS.md`, `docs/spec/00-stack.md`, `docs/spec/07-git-commits.md` (Sections 12.1 and 12.2)
*Acceptance:* `make up && python -c "from falkordb import FalkorDB; print(FalkorDB().select_graph('t').query('RETURN 1').result_set)"` prints `[[1]]`. Record the pinned image tag in `DECISIONS.md`.

**T1. FalkorDB capability probe.** `scripts/probe_falkordb.py` uses scratch graphs `probe_a` and `probe_b` (deleted at the end) and prints PASS/FAIL per item, writing `probe_results.json`:
F1 async client (`falkordb.asyncio`) works with 20 concurrent queries · F2 two graphs are isolated, `GRAPH.LIST` shows both, `GRAPH.DELETE` works · F3 vector index: create with dimension 8 (cosine), insert 3 vectors with `vecf32`, `db.idx.vector.queryNodes` returns nearest first, `node.embedding` comes back as a list of floats, a `MATCH ... WHERE` after `YIELD` works (print the raw `score` values for information) · F4 `sum(CASE ...)` and `count(DISTINCT CASE ... END)` inside aggregates · **F5 write atomicity:** 1 OPEN task and 50 concurrent copies of `Q-TASK-CLAIM`; PASS only if exactly 1 total row is returned across all copies; also 20 tasks with 10 concurrent `Q-TASK-CLAIM-NEXT` workers, PASS only if no task id is returned twice · F6 range index, `MERGE` of a relationship with `SET` · F7 unique constraint via `GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE <label> PROPERTIES 1 <prop>` (needs the range index first); a duplicate `CREATE` must fail (print the raw error text) · F8 `UNWIND ... MATCH ... CREATE` pattern and list properties (`steps`) round-trip · F9 full-text index create and query (fallback readiness) · F10 informational: write throughput to one graph versus two graphs under the same concurrent workload.
*Read first:* `docs/spec/02-memory-queries-rules.md` (Sections 4.3, 4.5, 6.5), `docs/spec/00-stack.md`
*Acceptance:* `make probe` exits 0 and prints the table. **Then record in `DECISIONS.md`:** async client yes/no, vector recall path (`vector` or `fulltext` fallback), write atomicity (yes, or use the lock fallback), unique constraints (yes, or use the MERGE fallback).

**T2. Core: config, clock, errors, tenancy, DB layer.** `memory_core/{config,clock,errors,tenancy,db}.py`. `tenancy.py`: `validate_tenant_id`, `graph_name`, allowed tenants from env. `db.py`: `TenantDB` (one per tenant, pooled, semaphore `MAX_INFLIGHT`, `run_ro`, `run_rw`, timing in ms, `delete_graph`); a registry returning one `TenantDB` per tenant.
*Read first:* `docs/spec/00-stack.md`, `docs/spec/01-data.md` (Section 1.1), `docs/spec/02-memory-queries-rules.md` (Section 6.5)
*Acceptance:* `pytest tests/test_tenancy.py`: valid ids pass; `"acme; DROP"`, `"A"`, `"ac"`, `"1abc"`, a 40-char id are rejected; graph name for `acme` is `mem_acme`; `now()` honors `CLOCK_NOW`; more than `MAX_INFLIGHT` concurrent calls never exceed the limit (use a counting stub).

**T3. Embedder.** `memory_core/embedder.py`: tokenizer, stemmer, mock embedder, `cosine`, Gemini embedder (`google-genai` `embed_content`, dimension from env, L2-normalize), factory from `EMBED_PROVIDER`.
*Read first:* `docs/spec/02-memory-queries-rules.md` (Section 5.1), `docs/spec/01-data.md` (Section 3 G2)
*Acceptance:* `pytest tests/test_embedder.py` asserts: the stem examples listed in Section 5.1; `tokens("INV-1042")` gives `["inv","1042"]`; mock embeddings are deterministic and unit length; with `EMBED_DIM=4096`, `cosine(embed(Q1), embed(ep-p1 summary))` is about 0.555, with `ep-p3 summary` about 0.267 and with `ep-p2 summary` exactly 0.0 (tolerance 0.02); the factory returns the mock when `EMBED_PROVIDER=mock` and the Gemini embedder otherwise (stub the client, no network).

**T4. Schema and seed.** `memory_core/schema.py` (`ensure_tenant`: indexes, vector indexes with `EMBED_DIM`, unique constraints per probe), `seed/data/{acme,globex}.json` (Section 2 of `01-data.md`), `seed/seed.py` (`--reset`, idempotent, `seed_tenant(tenant_id)`).
*Read first:* `docs/spec/01-data.md` (Sections 1, 2, 3 G1), `docs/spec/00-stack.md`
*Acceptance:* `make seed` prints per-tenant counts matching G1; running `make seed` a second time leaves all counts unchanged; `pytest tests/test_seed.py` asserts every G1 count for both tenants, that no node has an `embedding` property returned by `/graph`-style exports, and that every Fact is `HAS_FACT` of exactly one user.

**T5. History and semantic memory.** `memory_core/history.py` (`create_session`, `append_message`, `get_messages`) and `memory_core/semantic.py` (`remember_fact`, `get_profile`, `get_history`) with their queries.
*Read first:* `docs/spec/02-memory-queries-rules.md` (Sections 4.1, 4.2, 5.3), `docs/spec/01-data.md` (G4, G5, G14)
*Acceptance:* `pytest tests/test_history.py tests/test_semantic.py`: G4, G5, G14; additionally 10 concurrent `remember_fact(city, X_i)` with different objects leave **exactly one** ACTIVE `city` fact for the user; unknown predicate gives `INVALID_INPUT`.

**T6. Recall and consolidation.** `memory_core/recall.py` (Section 5.2) and `memory_core/consolidation.py` (`close_session`, Section 5.4).
*Read first:* `docs/spec/02-memory-queries-rules.md` (Sections 4.3, 5.2, 5.4), `docs/spec/01-data.md` (G2, G3, G9)
*Acceptance:* `pytest tests/test_recall.py tests/test_consolidation.py`: G2 (ordering, boosts, ACTIVE-only facts, procedures), G3, G9; no cross-user or cross-tenant id appears in any result; archived episodes are excluded after `decay` (can be run after T7; mark that assertion `xfail` until then and remove the mark in T7).

**T7. Procedural memory and decay.** `memory_core/procedural.py`: `find_procedures`, `record_outcome`, `promote_procedures`, `deprecate_procedures`, `should_deprecate`, `decay`.
*Read first:* `docs/spec/02-memory-queries-rules.md` (Sections 4.4, 5.5), `docs/spec/01-data.md` (G6, G10)
*Acceptance:* `pytest tests/test_procedural.py`: G6, G10 (including the second `promote_procedures()` returning `[]`); `should_deprecate` truth table (`(0,5)`, `(1,4)` deprecate; `(3,2)`, `(0,4)` do not); candidates are excluded from `recall` but included by `find_procedures(include_candidates=True)`.

**T8. Coordination.** `memory_core/coordination.py`: tasks (`create_task`, `claim_task`, `claim_next`, `complete_task`), shared state (`get_state`, `set_state`), routing (`route`), handoffs (`create_handoff`, `accept_handoff`, `complete_handoff`, `pending_handoffs`).
*Read first:* `docs/spec/02-memory-queries-rules.md` (Sections 4.5, 6), `docs/spec/01-data.md` (G7, G8, G11, G12)
*Acceptance:* `pytest tests/test_coordination.py`: G7, G8 (state machine, FORBIDDEN, CONFLICT, 10 concurrent accepts give 1 success), G11, G12; plus 20 concurrent `set_state` CAS increments end at exactly 20.

**T9. MCP server.** `memory_mcp/{server,context,allowlist,envelope,models}.py` with the 16 tools of Section 7, context checks, role allowlists enforced server-side.
*Read first:* `docs/spec/03-mcp-tools.md`, `docs/spec/01-data.md` (G13), `docs/spec/02-memory-queries-rules.md` (Section 5)
*Acceptance:* `pytest tests/test_mcp_tools.py tests/test_schema_simple.py tests/test_isolation.py`: spawns the server over stdio via the MCP client; lists 16 tools with non-empty descriptions containing `Use when:` and `Do not use when:`; every tool schema passes `assert_simple_schema` after stripping the four context fields (write `backend/llm/schema.py` first if not present: it is specified in `docs/spec/04-agent-llm-api.md` Section 8.2.1); each tool runs and returns an envelope for the acme scenario inputs; G13 items: `agent-triage` calling `accept_handoff` gives `FORBIDDEN`, `tenant_id="acme; DROP"` gives `INVALID_INPUT`, a session of another user gives `FORBIDDEN`, recall as rahul returns no priya data; 20 parallel `recall_memory` calls over one MCP session all succeed.

**T10. LLM adapter and Gemini probe.** `backend/llm/{base,schema,gemini_client,fake_client}.py` as in `docs/spec/04-agent-llm-api.md` Sections 8.2 to 8.2.2. `scripts/probe_gemini.py` does, in order: (1) **introspection, no key needed:** print the field names of `types.AutomaticFunctionCallingConfig`, `types.ThinkingConfig`, `types.GenerateContentConfig`, `types.FunctionDeclaration`, `types.EmbedContentConfig` from the installed `google-genai` (`.model_fields.keys()`); compare with the recipe (`disable`, `thinking_level`, `parameters_json_schema`, `system_instruction`, `automatic_function_calling`, `thinking_config`, `output_dimensionality`) and fix the recipe in code if any name differs, logging it in `DECISIONS.md`; (2) if `GEMINI_API_KEY` is unset print `SKIPPED live checks (no key)` and exit 0; (3) round trip with a fake `add` tool; (4) two sequential tool calls with **no 400 error** (proves thought signatures are preserved); (5) all real MCP tool schemas (context fields stripped) in one request; (6) one `embed_content` call returning a vector of the requested dimension.
*Read first:* `docs/spec/04-agent-llm-api.md` (Sections 8.2, 8.2.1, 8.2.2, 8.2.3)
*Acceptance:* `python scripts/probe_gemini.py` exits 0. `pytest tests/test_llm_gemini.py`, using a **stubbed** `genai.Client`: (a) the model's `Content` is appended to history **unchanged** (identity check); (b) several function calls produce **one** results `Content` in the same order; (c) retry on a simulated 429, no retry on a simulated 400; (d) `thinking_level="minimal"` is rejected by our config validation before any API call; (e) `simplify_schema` inlines `$ref`, removes `title`/`default`, and converts `anyOf [X, null]` to `X` using fixture schemas.

**T11. Bridge, events, mock scenarios, crew runner, CLI.** `backend/{events,mcp_bridge,agent_mock,scenarios,crew}.py`, `scripts/run_scenario.py <scenario> --mode mock`.
*Read first:* `docs/spec/04-agent-llm-api.md` (Sections 8.1, 8.4, 8.5, 8.8), `docs/spec/03-mcp-tools.md`
*Acceptance:* `python scripts/run_scenario.py continuity --mode mock` ends with a `final` event and writes `replays/continuity.jsonl`; same for `fact_update` and `procedure_learning` (after `make reset` between runs). `pytest tests/test_agent_mock.py` asserts through events **and** direct graph reads: G2 (first `recall_result` episode is `ep-p1`), G4, G8 (carries total 8 with counts), G9, G10; the LLM-visible `ToolSpec`s contain none of the four context fields; a bridge call whose args include `tenant_id="globex"` runs in acme and emits a `warning`; the bridge hides non-allowlisted tools; every `memory_visit` node id exists in the tenant graph.

**T12. Live agent loop (Gemini).** `backend/agent_live.py`, `backend/prompts.py` per Sections 8.3, 8.2.3, 8.6.
*Read first:* `docs/spec/04-agent-llm-api.md` (Sections 8.2.3, 8.3, 8.4, 8.6, 8.8)
*Acceptance:* `pytest tests/test_agent_live.py` using `FakeSession` with scripted turns that call the real MCP tools: asserts the 10-call cap, repeated-call abort, tool errors fed back with `is_error`, all agent text saved as messages, handoff chaining (`handoff_created` triggers the specialist turn), specialised events built from envelopes. **If `GEMINI_API_KEY` is set:** `AGENT_MODE=live python scripts/run_scenario.py continuity` ends with the handoff COMPLETED and an episode `ep-sess-demo-continuity` created. If no key, write "live Gemini run not verified" in `BUILD_LOG.md` (never claim it passed).

**T13. REST API, auth, SSE.** `backend/{main,auth}.py` per Section 8.7.
*Read first:* `docs/spec/04-agent-llm-api.md` (Sections 8.7, 8.8), `docs/spec/01-data.md` (G13)
*Acceptance:* `pytest tests/test_api.py` (httpx + SSE): 401 without key; **403** for acme key on `/t/globex/...`; `POST /t/acme/sessions` with `scenario=continuity` streams `agent_active` for triage then billing, a `handoff` COMPLETED and `session_closed`; `GET .../messages` returns the 3 persisted messages; **restart persistence:** after rebuilding the app object and clients from scratch (same FalkorDB), recall for priya returns the same top-1 and the new episode is present; `GET /t/acme/isolation-check` returns all checks passed; no response body anywhere contains the key `embedding`.

**T14. Load test.** `memory_core/loadtest.py`, `scripts/load_test.py`, admin endpoints in the API, `tests/test_load_small.py` (scaled down: C1 with 20 claimants, C2 with 40 tasks and 5 workers, C3 with 5 workers x 5).
*Read first:* `docs/spec/06-load-evals-docs.md` (Section 10.1), `docs/spec/01-data.md` (G15)
*Acceptance:* `python scripts/load_test.py` exits 0, prints C1 to C5 PASS with real latency numbers, and writes `evals/load_results.md` (including the one-graph versus two-graph measurement, reported honestly); `pytest tests/test_load_small.py` passes.

**T15. Frontend scaffold and graph.** Vite app, Tailwind, shadcn components, API client with `X-API-Key`, tenant switcher, memory graph with dagre layout and node components.
*Read first:* `docs/spec/05-frontend.md`, `docs/spec/04-agent-llm-api.md` (Sections 8.7, 8.8 types)
*Acceptance:* `npm run build` and `npx tsc --noEmit` succeed.

**T16. Streaming UI, tabs, proof, replay.** Event reducer (pure, tested), SSE hook, chat panel, trace feed, highlight logic (recall glow, supersession fade, handoff animation, promotion badge), memory tabs, Proof tab (isolation, load test), replay toggle.
*Read first:* `docs/spec/05-frontend.md`, `docs/spec/04-agent-llm-api.md` (Section 8.8)
*Acceptance:* `npx vitest run` passes the reducer tests of Section 9 using the three recorded replay files; `npm run build` succeeds.

**T17. Evals.** `evals/{scenarios.yaml,run_evals.py,ablation.py}` per Section 10.2.
*Read first:* `docs/spec/06-load-evals-docs.md` (Section 10.2)
*Acceptance:* `make eval` writes `evals/results.md` with the table; mock mode passes 100%; the persistence check passes; `ablation.py` runs only with a key and `--live` (otherwise prints a skip message).

**T18. Documentation, CI, deployment.** `README.md` (Section 11.1), `docs/queries.md` (every query with a plain-English explanation and the golden result it produces), `docs/architecture.md` (Mermaid: architecture, graph schema, sequence for `continuity`, handoff state machine), `AI_DISCLOSURE.md` (copied into the README), `.github/workflows/ci.yml`, Dockerfiles and a full-stack `docker-compose.yml` (optional hosting; if not deploying, the compose file must still work locally).
*Read first:* `docs/spec/06-load-evals-docs.md` (Section 11), `docs/spec/00-stack.md`
*Acceptance:* a fresh clone follows the README only: `cp .env.example .env && make up && make seed && make test && make dev` and `make web` work (record in `BUILD_LOG.md`); `docker compose up --build` then `curl localhost:8000/health` returns ok.

**T19. Owner handoff.** `docs/EXPLAINER.md` (plain-language walkthrough: why graph per tenant, the three memory types and how each updates, why conditional writes act as locks, hybrid recall, the handoff protocol, where the graph is load-bearing, which probe fallbacks were used), `docs/OWNER_QUESTIONS.md` (20 questions a judge may ask with short model answers), `docs/demo_script.md` (timed script from Section 11.3), plus a list of manual tasks the human must do.
*Read first:* `docs/spec/06-load-evals-docs.md` (Section 11.3)
*Acceptance:* files exist; EXPLAINER references real function names that exist (grep check).

---

## Definition of Done

- [ ] `make up seed test` passes from a fresh clone; all golden values (G1 to G15) are asserted by tests.
- [ ] Scenarios `continuity`, `fact_update`, `procedure_learning` run headless in mock mode with the expected outcomes; live Gemini mode verified with a real key (or explicitly logged as unverified).
- [ ] Isolation proof (tenant, user, API key, role allowlist) passes; load test C1 to C5 pass with real numbers recorded.
- [ ] UI renders the memory graph, streams events, shows supersession and handoff animations, tabs and proof work, replay works.
- [ ] README contains setup, graph model, memory types, all key queries, concurrency model, AI disclosure and the track name.
- [ ] `DECISIONS.md` records: pinned image tag, probe outcomes, fallbacks used, any deviation.
- [ ] `BUILD_LOG.md` has real command outputs for every task.
- [ ] No real or private data anywhere; `.env` not committed.
- [ ] Human-owner docs (T19) written.
- [ ] Only libraries from `docs/spec/00-stack.md` are used; lockfiles committed; CI workflow green.
- [ ] `scripts/probe_gemini.py` exits 0; `tests/test_llm_gemini.py` and `tests/test_schema_simple.py` pass; no file outside `backend/llm/` and `memory_core/embedder.py` imports `google.genai` or `anthropic`.
- [ ] Git history follows `docs/spec/07-git-commits.md`: 45+ conventional commits, pushed throughout, tags `v0.1-core`, `v0.2-memory`, `v0.3-agents`, `v0.4-ui`, `v1.0`, no backdating, no force-push, first commit after Oct 15 12:01 AM IST.
