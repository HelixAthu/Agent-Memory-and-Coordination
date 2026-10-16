# Architectural Decisions Log

Format: `date | decision | reason`

2026-10-15 | Tenancy model: one FalkorDB graph per tenant (`mem_<tenant_id>`) | Enforces physical graph isolation without relying on property filters.
2026-10-15 | Injected context fields (`tenant_id`, `user_id`, `agent_id`, `session_id`) | Prevents LLM prompt injection and hallucinated tenant access.
2026-10-15 | FalkorDB pinned Docker image `falkordb/falkordb:v4.22.1` | Ensures reproducible GraphBLAS and vector index execution.
