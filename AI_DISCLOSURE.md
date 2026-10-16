# AI Assistance Disclosure

## Project: Memory Fabric
- **Track:** Agent Memory and Coordination (Graph Hacks 2026)

## Disclosure Details
In accordance with Graph Hacks submission rules, AI tooling was utilized during development:
- **Coding Assistant:** Antigravity (Google DeepMind) was used for scaffolding, implementing Cypher traversals, drafting test suites, and formatting documentation.
- **Model Integration:** Gemini `gemini-3.8-flash` via `google-genai` powers live multi-turn agent execution and tool calling.
- **Verification:** All tests, vector index queries, concurrency stress tests, and golden datasets were independently validated against local FalkorDB instances.
