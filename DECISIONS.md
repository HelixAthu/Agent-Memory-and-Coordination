# Architectural Decisions Log

Format: `date | decision | reason`

2026-10-15 | Tenancy model: one FalkorDB graph per tenant (`mem_<tenant_id>`) | Enforces physical graph isolation without relying on property filters.
2026-10-15 | Injected context fields (`tenant_id`, `user_id`, `agent_id`, `session_id`) | Prevents LLM prompt injection and hallucinated tenant access.
2026-10-15 | FalkorDB pinned Docker image `falkordb/falkordb:v4.22.1` | Ensures reproducible GraphBLAS and vector index execution.
2026-10-15 | Async client: falkordb.asyncio verified | Probe F1 passed with 20 concurrent async queries.
2026-10-15 | Vector index: native HNSW vector index enabled | Probe F3 verified cosine similarity and post-yield status filtering.
2026-10-15 | Write atomicity: native Cypher write query serialization verified | Probe F5 confirmed exactly 1/50 concurrent claimants won; lock fallback not needed.
2026-10-15 | Unique constraints: MERGE ON CREATE fallback active for StateEntry | Probe F7 showed explicit unique constraints unsupported; Section 6.5 MERGE fallback used.
2026-10-16 | Gemini SDK introspection: google-genai field names verified | All recipe field names (disable, thinking_level, parameters_json_schema, system_instruction, automatic_function_calling, thinking_config, output_dimensionality) match installed SDK exactly.
