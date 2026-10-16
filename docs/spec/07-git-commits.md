# Spec 07: Git workflow and commit plan

- **Purpose:** Defines commit rules, the commit-by-commit plan, push cadence.
- **Read this when:** starting work (skim), and before every commit.

> **File map note:** section numbers are global across the spec files. `AGENTS.md` has the index.

---

## 12. Git workflow and commit plan

### 12.1 Principles (hard rules)

1. **Honest history.** Never backdate commits (`--date`, `GIT_AUTHOR_DATE`, etc.), never fabricate a history by splitting a finished project into fake commits afterward, and never rewrite history after pushing (no `--amend` on pushed commits, no `push --force`). The first commit must be made after the hackathon starts (Oct 15, 12:01 AM IST).
2. **One logical change per commit.** A commit should be explainable in one line. Do not mix unrelated changes (for example seed data and frontend styling).
3. **Every commit leaves the repo working.** Run the relevant tests (`make test`, or `npm run build` for frontend work) before committing. If a commit would break the build, finish the work first.
4. **Review before committing.** Run `git diff --staged` and read it. Remove debug prints and dead code. This is also how the human owner stays able to explain the code.
5. **Conventional commit messages:** `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:` with an optional scope, imperative mood, under 72 characters, e.g. `feat(queries): add attacker path to PII databases`.
6. **Push after every task**, and at least every few commits (`git push origin main`). Work directly on `main` (solo) or on short-lived branches merged via PR (team of 2 to 4; then use `feat/<area>` branches, merged with merge commits, not squashes).
7. **Keep fix commits visible.** Bug fixes found during testing stay as their own commits (for example `fix(mcp): reject max_hops above 6`). Do not squash them away.
8. **Never commit:** `.env`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`, `outbox/*.jsonl`, `probe_results.json` (add to `.gitignore` in the first commit). Do commit: lockfiles, `.env.example`, replay files in `replays/`.
9. **Tag milestones** (annotated tags, pushed): `v0.1-core`, `v0.2-memory`, `v0.3-agents`, `v0.4-ui`, `v1.0`.
10. **Log it.** In `BUILD_LOG.md`, list the commit hashes (`git log --oneline`) under each task heading.

### 12.2 Setup (before T0 content; this is commit 1)

```
git init -b main
# create the GitHub repo (public) and: git remote add origin <url>
```
If you cannot create or push to a remote, commit locally and tell the owner exactly which commands to run to push (do not stop work).

### 12.3 Commit plan (target 45 to 60 commits; adjust sensibly but keep the granularity)

| # | Commit message | Task |
|---|---|---|
| 1 | `chore: initialize repo with README stub, license and .gitignore` | T0 |
| 2 | `docs: add problem statement and memory graph schema` | T0 |
| 3 | `chore: add docker-compose for pinned FalkorDB` | T0 |
| 4 | `chore: scaffold python project, requirements and Makefile` | T0 |
| 5 | `chore: add falkordb capability probe` | T1 |
| 6 | `docs: record probe results and pinned image tag` | T1 |
| 7 | `feat(core): config, clock and tenant id validation` | T2 |
| 8 | `feat(core): per-tenant graph connection with pooled async client` | T2 |
| 9 | `test(core): tenancy and clock tests` | T2 |
| 10 | `feat(core): tokenizer, stemmer and mock embedder` | T3 |
| 11 | `feat(core): gemini embedder behind EMBED_PROVIDER` | T3 |
| 12 | `test(core): embedder and cosine tests` | T3 |
| 13 | `feat(core): schema, indexes and constraints per tenant` | T4 |
| 14 | `feat(seed): acme agents, users, entities and sessions` | T4 |
| 15 | `feat(seed): acme episodes, facts, procedures and tasks` | T4 |
| 16 | `feat(seed): globex tenant data` | T4 |
| 17 | `feat(seed): idempotent seed script with --reset` | T4 |
| 18 | `test(seed): golden counts G1`; tag `v0.1-core` | T4 |
| 19 | `feat(history): atomic message append and history chain` | T5 |
| 20 | `feat(semantic): remember_fact with supersession and reinforcement` | T5 |
| 21 | `test(semantic): supersession and concurrency tests G4 G5 G14` | T5 |
| 22 | `feat(recall): hybrid vector and graph recall with scoring` | T6 |
| 23 | `test(recall): golden recall G2 G3` | T6 |
| 24 | `feat(consolidation): close_session episode creation and fact extraction` | T6 |
| 25 | `test(consolidation): golden G9` | T6 |
| 26 | `feat(procedural): outcomes, promotion, deprecation and decay` | T7 |
| 27 | `test(procedural): promotion and decay goldens G6 G10` | T7 |
| 28 | `feat(coord): task claiming and shared-state CAS` | T8 |
| 29 | `feat(coord): routing and handoff protocol` | T8 |
| 30 | `test(coord): goldens G7 G8 G11 G12`; tag `v0.2-memory` | T8 |
| 31 | `feat(mcp): server skeleton, context checks and envelope` | T9 |
| 32 | `feat(mcp): memory read tools` | T9 |
| 33 | `feat(mcp): memory write and coordination tools` | T9 |
| 34 | `feat(mcp): role allowlists and server-side enforcement` | T9 |
| 35 | `test(mcp): tool contracts, schema simplicity and isolation G13` | T9 |
| 36 | `feat(llm): provider-neutral interface and tool schema simplifier` | T10 |
| 37 | `feat(llm): gemini session with thought-signature handling` | T10 |
| 38 | `chore: gemini probe script` | T10 |
| 39 | `feat(agent): event bus and bridge with context injection` | T11 |
| 40 | `feat(agent): scripted mock scenarios` | T11 |
| 41 | `feat(agent): crew runner with handoff chaining` | T11 |
| 42 | `feat(agent): live gemini turn loop and prompts` | T12 |
| 43 | `feat(api): tenant api keys and routes` | T13 |
| 44 | `feat(api): sessions, messages and sse stream` | T13 |
| 45 | `test(api): end to end scenario, 403 isolation and restart persistence`; tag `v0.3-agents` | T13 |
| 46 | `feat(load): concurrency load test and invariants` | T14 |
| 47 | `docs: record load results` | T14 |
| 48 | `chore(web): scaffold vite, tailwind and shadcn` | T15 |
| 49 | `feat(web): tenant switcher and memory graph rendering` | T15 |
| 50 | `feat(web): event reducer and sse hook with tests` | T16 |
| 51 | `feat(web): chat panel and trace feed` | T16 |
| 52 | `feat(web): graph highlighting for recall, supersession and handoff` | T16 |
| 53 | `feat(web): memory tabs` | T16 |
| 54 | `feat(web): proof tab for isolation and load test` | T16 |
| 55 | `feat(web): replay mode`; tag `v0.4-ui` | T16 |
| 56 | `feat(evals): scenario harness, ablation and results` | T17 |
| 57 | `docs: query reference with golden results` | T18 |
| 58 | `docs: readme with graph model, memory types and ai disclosure` | T18 |
| 59 | `chore: github actions ci` | T18 |
| 60 | `chore: dockerfiles and full-stack compose` | T18 |
| 61 | `docs: explainer, owner questions and demo script` | T19 |
| 62+ | Real fix commits found during testing, then `docs: add demo video link`; tag `v1.0` | T19 |

### 12.4 Push cadence
- Push at the end of each task (T0 to T19) and before any long-running step.
- Expect at least 5 pushes on each day. If work has gone more than 90 minutes without a commit, the change is probably too large; split it.
- After the final push, verify from a **fresh clone** in a temporary directory that the README setup works, and log the result.

### 12.5 What not to do
- Do not create a single huge commit ("initial implementation") and do not create dozens of empty or trivial commits to pad history.
- Do not commit generated build output or secrets. If a secret is ever committed, **stop**, rotate it, tell the owner, and do not attempt to hide it by rewriting pushed history.
- Do not edit commit timestamps, and do not make commits from before the hackathon window.
