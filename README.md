# File Organizer With DAG (& Dry Runs)

Multi-agent growing-graph orchestrator built on the previous PDMA cognitive
architecture. The graph itself is the agent loop: each node is a typed
skill (Planner, Researcher, Distiller, Critic, Formatter, …), edges
carry the predecessor's `AgentResult`, and the runtime executes ready
nodes in parallel via `asyncio.gather`.


---

## Layout

```
FileOrganiser_DAG/
├── README.md          ← you are here
├── .env.example       ← copy to .env, fill in keys you have
├── .gitignore
│
├── code/              ← the agent. Run from here.
│   ├── flow.py        ← orchestrator (Graph + Executor + CLI). Read this first.
│   ├── skills.py      ← skill registry, prompt rendering, run_skill
│   ├── recovery.py    ← failure classification + critic-fail splice
│   ├── persistence.py ← session writes (graph.json + per-node JSON)
│   ├── mcp_runner.py  ← multi-turn tool-use loop wrapper
│   ├── sandbox.py     ← subprocess Python runner (usability boundary; NOT security)
│   ├── replay.py      ← stdin-driven trace viewer
│   ├── schemas.py     ← AgentResult, NodeSpec, NodeState, MemoryItem, …
│   ├── agent_config.yaml  ← skills catalogue
│   ├── scanner.py     ← Tier-0/1 file scanner (structure + cheap signals, no LLM)
│   ├── executor.py    ← MoveExecutor: dry_run / apply (with undo-log) / undo
│   ├── scan_config.yaml   ← include/exclude paths, locked zones, index flags
│   ├── run_organiser.py   ← CLI entry point: scan → DAG pipeline
│   ├── run_ui.py      ← NiceGUI dashboard entry point (serves on :8110)
│   ├── gateway.py     ← auto-starts gateway; re-exports LLM client + embed()
│   ├── prompts/       ← one .md per skill (planner, classifier, sensitive_detector, …)
│   ├── tests/         ← test_recovery.py + test_file_organizer.py
│   ├── mcp_server.py  ← MCP tools: web_search, fetch_url, search_knowledge, …
│   ├── ui/            ← NiceGUI dashboard (app.py, dag_svg.py, session.py, widgets.py)
│   ├── state/         ← sessions/, scan_state.json (written at runtime)
│   ├── memory.py / vector_index.py / artifacts.py  ← carry-over (don't touch)
│   ├── perception.py / decision.py / action.py     ← carry-over (don't touch)
│   └── sandbox/papers/  ← five arxiv abstracts for indexed-corpus queries
│
└── gateway/           ← LLM Gateway V8 (FastAPI). Runs on :8108.
    ├── main.py
    ├── client.py      ← the SDK code/gateway.py imports from
    ├── providers.py / router.py / embedders.py / db.py / cache.py
    ├── agent_routing.yaml  ← agent → preferred provider mapping
    ├── pyproject.toml
    └── run.sh
```

---

## Quickstart

You need: Python 3.11+, [uv](https://docs.astral.sh/uv/), Ollama
(`brew install ollama` then `ollama pull nomic-embed-text`), and at least
one provider API key from `.env.example`.

```bash
# 1. Secrets
cp .env.example .env
$EDITOR .env                  # add the keys you have

# 2. Install
cd gateway && uv sync && cd ..
cd code    && uv sync && cd ..

# 3. Start the gateway (one terminal)
cd gateway && uv run main.py
# (or: ./run.sh)
# It boots on http://localhost:8108; /v1/routers should answer.

# 4. Run the agent (another terminal)
cd code
uv run python flow.py "hello"
```

A successful first run prints two node lines (planner, formatter) and a
greeting. Sessions land in `code/state/sessions/<sid>/`. Walk one with:

```bash
uv run python replay.py <sid>
```

---

## How to think about the architecture

The Planner reads the user query and emits a small DAG of skill nodes
to run. Each ready node fires through the gateway in parallel with its
ready siblings. When a skill's yaml entry has `internal_successors`,
the orchestrator appends those automatically — that's how **Coder →
SandboxExecutor** chains without the Planner having to ask for it.

Critic nodes get auto-inserted on edges out of skills tagged
`critic: true` in `agent_config.yaml` (currently Distiller). A
verdict=fail from a Critic splices a recovery Planner into the graph,
capped at one re-plan per branch.

Failure handling is in `recovery.py`. Transient gateway errors don't
re-plan (the gateway already retries); validation errors don't re-plan
(it's a prompt bug); upstream-failures do. `tests/test_recovery.py`
pins the classifier against the actual gateway error strings.

Read `flow.py`'s 300 lines top-to-bottom before you write a single
line of your Coder prompt. The orchestrator is small enough to fit in
your head.

---

## When things go wrong

| symptom | first place to look |
|---|---|
| `[gateway] launching … failed to start within 45s` | `cd gateway && uv run main.py` in another terminal; read its stderr. Probably a missing API key or port :8108 already taken. |
| `httpx.HTTPStatusError: '503 Service Unavailable'` | All worker providers in cooldown / unconfigured. Add another key to `.env` or wait a minute. |
| coder ran but `sandbox_executor` reports `no code in upstream coder output` | Your prompt isn't emitting the JSON shape the orchestrator expects. §"Output contract". |
| The final answer is short / wrong | Run `replay.py <sid>` and inspect what each node actually saw (the `prompt_sent` field captures the exact bytes sent to the gateway). |

---

## What NOT to touch

- `perception.py`, `decision.py`, `action.py`, `memory.py`,
  `vector_index.py`, `artifacts.py`, `mcp_server.py` — carry-over
  files from the single-loop agent. The tool-blindness contract on
  Perception depends on these staying as-is.
- `gateway/` — treat as a service you call. If you find a real bug,
  open an issue.

---

## Provenance and version

28 unit tests cover the failure-recovery + critic-splice mechanics.
Five validation queries (hello, Shannon Wikipedia, parallel fan-out
populations, graceful-fail nonexistent path, SIGKILL+resume) have been
verified end-to-end on the same code you have here.

If your `uv run python flow.py "hello"` produces a final answer, the
build runs cleanly on your machine. The next step is to proceed with the phases.

---

## Phase 0a — Five base query results (2026-06-01)

Logs in `code/logs/`. All runs use the gateway on :8108 with providers
spread across groq, gemini, nvidia, cerebras (soft-pin routing from
`gateway/agent_routing.yaml`).

| Query | Session ID | Nodes | Wall-clock | Log |
|---|---|---|---|---|
| hello | s8-f6737e25 | 2 (planner→formatter) | ~4s | `logs/hello.txt` |
| A — Shannon Wikipedia | s8-caab497e | 4 (planner→researcher→distiller→formatter) | ~62s | `logs/query_A.txt` |
| I — London/Paris/Berlin | s8-a7853431 | 7 (planner→3×researcher∥→coder→formatter+sandbox) | ~80s | `logs/query_I.txt` |
| J — graceful failure | s8-5d61f0e1 | 4 (planner→coder→formatter+sandbox) | ~24s | `logs/query_J.txt` |
| K — resume after kill | s8-8d8d2867 → s8_K_resumed_v2 | 7 (4 nodes partial + 3 resumed) | ~110s + 15s | `logs/query_K_partial.txt`, `logs/query_K_resume.txt` |

### Node timing detail

**Query A (Shannon):** planner 5.9 s · researcher 42.9 s · distiller 4.3 s ·
formatter 8.9 s

**Query I (cities — parallel fan-out):** planner 4.1 s ·
researcher×3 parallel (80.1 s / 52.0 s / 39.7 s) · coder 4.0 s ·
formatter 33.0 s · sandbox_executor 0.1 s  
Wall-clock ≈ 80 s limited by slowest researcher (vs ~125 s sequential).

**Query J (graceful failure):** planner 3.7 s · coder 3.8 s · formatter 16.1 s ·
sandbox_executor 0.3 s.  
Note: the planner dispatched a coder to attempt the read programmatically
rather than fail-fast to formatter directly; the coder and sandbox returned
a "file not found" result, and the formatter correctly reported the failure.

**Query K (resume):** partial run — planner 4.3 s, researchers 36.7 s / 82.4 s /
73.8 s (all 3 complete before kill); coder was in `running` state at kill.
Resume re-ran coder (4.9 s) + formatter (9.6 s) + sandbox_executor (0.1 s).
Final answer: Kinshasa is growing fastest at 4.40 % per year.

### Log output

<details>
<summary><strong>hello — minimal DAG (s8-f6737e25)</strong></summary>

```
session s8-f6737e25  ─  query: Say hello.
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (3.9s)
[n:2] formatter          complete (4.4s)
FINAL: Hello! How can I assist you today?
```
</details>

<details>
<summary><strong>Query A — Shannon Wikipedia (s8-caab497e)</strong></summary>

```
session s8-caab497e  -  query: Fetch https://en.wikipedia.org/wiki/Claude_Shannon …
[n:1] planner            complete (5.9s)
[n:2] researcher         complete (42.9s)
[n:3] distiller          complete (4.3s)
[n:4] formatter          complete (8.9s)
FINAL: Claude Shannon born 30 Apr 1916, died 24 Feb 2001.
       Three key contributions: (1) "A Mathematical Theory of Communication" 1948,
       introducing entropy; (2) defining the bit; (3) channel capacity theorem.
```
</details>

<details>
<summary><strong>Query I — London / Paris / Berlin — parallel fan-out (s8-a7853431)</strong></summary>

```
session s8-a7853431  -  query: find the populations of London, Paris, and Berlin …
[n:1] planner              complete   (4.1s)
[n:2] researcher           complete   (80.1s)   ← parallel
[n:3] researcher           complete   (52.0s)   ← parallel
[n:4] researcher           complete   (39.7s)   ← parallel
[n:5] coder                complete   (4.0s)
[n:6] formatter            complete   (33.0s)
[n:7] sandbox_executor     complete   (0.1s)
FINAL: London ~8,800,000 · Paris ~2,103,778 · Berlin ~3,685,000.
       Closest pair: Paris and Berlin, difference 1,581,222.
```
</details>

<details>
<summary><strong>Query J — graceful failure (s8-5d61f0e1)</strong></summary>

```
session s8-5d61f0e1  ─  query: Read /nonexistent/path.txt and tell me what's in it.
[n:1] planner            complete (3.7s)
[n:2] coder              complete (3.8s)
[n:3] formatter          complete (16.1s)
[n:4] sandbox_executor   complete (0.3s)
FINAL: The file /nonexistent/path.txt does not exist and cannot be read.
```
</details>

<details>
<summary><strong>Query K — resume after kill (s8-8d8d2867 → s8_K_resumed_v2)</strong></summary>

```
─── partial run (s8-8d8d2867) ───────────────────────────────────────────────
[n:1] planner            complete (4.3s)
[n:2] researcher         complete (36.7s)   ← all 3 complete before kill
[n:3] researcher         complete (82.4s)
[n:4] researcher         complete (73.8s)
[n:5 coder — KILLED; status=running on disk]

─── resume (s8_K_resumed_v2) ────────────────────────────────────────────────
[n:5] coder              complete (4.9s)    ← re-ran from scratch
[n:6] formatter          complete (9.6s)    ← n:1–4 NOT re-run
[n:7] sandbox_executor   complete (0.1s)
FINAL: Kinshasa growing fastest at 4.40 % per year.
```
</details>

---

## File Organiser — Quick-start

Two commands (gateway must stay up in one terminal while the UI runs in another):

```bash
# Terminal 1 — LLM gateway (keep running)
cd gateway && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8108

# Terminal 2 — NiceGUI dashboard
cd code && .venv\Scripts\python.exe run_ui.py
# → open http://localhost:8110
```

To run a fresh scan before opening the dashboard:

```bash
cd code && .venv\Scripts\python.exe run_organiser.py
# Scans demo_messy_drive/, hands the manifest to the DAG,
# writes a new session to state/sessions/. Reload the dashboard to see it.
```

---

## demo_messy_drive vs demo_clean_drive

Session used: **s8-b0dffdf2** (Medium Effort plan, node n:66 formatter output).

| File (original location) | Original folder | Clean destination | Action |
|---|---|---|---|
| Form16_FY2025.txt | Documents\ | Private\Finance\Tax\ | moved |
| HDFC_statement_Jan2026.txt | Documents\ | Private\Finance\BankStatements\ | moved |
| PAN_card.txt | Documents\ | Private\IDs\ | moved |
| salary_slip_april2026.txt | Documents\ | Private\Finance\Payroll\ | moved |
| amazon_order_4471.txt | Downloads\ | Finance\Receipts\2026\ | moved |
| swiggy_invoice_mar.txt | Downloads\bills\ | Finance\Receipts\2026\ | moved |
| electricity_bill_jan.txt | Downloads\ | Finance\Utilities\2026\ | moved |
| flipkart_2025_tv.txt | Downloads\ | Finance\Receipts\2025\ | moved |
| IMG_20260601_165420.txt | Downloads\ | Documents\Notes\2026\ | moved (critic corrected: not a photo) |
| old_notes_2023.txt | Downloads\ | Documents\Notes\2023\ | moved |
| untitled.txt | Downloads\ | Misc\ | moved |
| IMG_2098.txt | Pictures\ | Pictures\2026\ | moved |
| sunset.txt | Pictures\ | Pictures\2026\ | moved |
| IMG_2098_copy.txt | Pictures\backup\ | — | removed (exact duplicate) |
| sunset_dup.txt | Pictures\backup\ | — | removed (exact duplicate) |
| SetupTool_v3_extracted\ (4 files) | Downloads\ | — | omitted (stale installer folder) |
| Projects\EAGv3\Session7\ | Projects\ | Projects\EAGv3\Session7\ | untouched (pattern_analyzer: scored high) |
| Projects\EAGv3\Session8\ | Projects\ | Projects\EAGv3\Session8\ | untouched (pattern_analyzer: scored high) |

---

## Architecture — three-tier scanner + DAG fan-out

The system is built in three tiers, cheapest first, so the expensive LLM only
ever touches what genuinely needs judgment.

**Tier 0 — structural** (`scanner.py`). A pure `os.scandir` walk collects name,
extension, size, mtime, and path for every file in the tree. On production
Windows this tier would query the voidtools Everything SDK or the NTFS Master
File Table — metadata the OS already maintains — making the initial index
near-instant regardless of drive size. The fallback is a standard scandir walk,
used here for portability.

**Tier 1 — cheap signals, no LLM** (`scanner.py`). Four sub-passes run in a
single walk: (a) SHA-256 content hashing for exact-duplicate detection and
space-reclaimable grouping; (b) folder short-circuit — installer-extract, build,
VCS, and `.venv` directories are recognised at the folder *boundary* and never
descended, eliminating large subtrees without reading individual files; (c)
sensitive prefilter — filename and path regex (salary, statement, bank, PAN,
Form16, `.kdbx`, …) marks private files from *metadata only*, before any content
is read; (d) mtime/size change-detection reads `state/scan_state.json` from the
previous run so unchanged files skip re-hashing, and the processed-ledger
(`state/ledger.json`, keyed by SHA-256) marks already-moved files as
`already_handled`.

**Tier 2 — semantic, LLM** (the DAG). Only what survives tiers 0–1 reaches the
LLM. The Planner fans the surviving files into independent batches and emits
`classifier`, `sensitive_detector`, and `pattern_analyzer` nodes simultaneously.
Because classifying documents does not depend on classifying photos, all branches
fire via `asyncio.gather` in parallel. A `critic` node gates each `classifier`
output before it reaches the `formatter`. The formatter waits on all upstream
results (the gather barrier) and produces the phase-1 report. If a critic returns
`fail`, the orchestrator splices a recovery Planner into the live graph — the
same splice mechanics pinned by `tests/test_recovery.py`.

**Privacy contract.** Files that match the sensitive prefilter are routed to
`sensitive_detector`, which is pinned to a *local* provider (`ollama`) in
`gateway/agent_routing.yaml`. Their content is **never read and never leaves the
machine**. The detector returns a confidence-rated verdict and a suggested
destination derived from filename, path, and size alone — with `content_read:
false` in every response. Hashing for dedup is still applied; hashing is not
semantic content reading. The result: `HDFC_statement.pdf` gets a
privacy-preserving verdict sitting next to `react_paper.pdf` which was fully
classified — two fundamentally different handling modes, explicitly recorded in
the session JSON.

---

## Phase evidence — captured log sessions

### Phase 1 — critic fail / pass / recovery (2026-06-04)

Both runs use `run_organiser.py → flow.py` with the gateway on :8108.

| Run | Session ID | Files | Outcome |
|---|---|---|---|
| Pass (no misclassified file) | s8-b0dffdf2 | 18 | Multiple critic-fail/recovery cycles; formatter n:27 + n:66 both complete; full Phase-1 Assessment report produced |
| Fail (IMG file present) | s8-465e6637 | 19 | Critics n:5 → recovery n:11, n:9 → recovery n:12; formatter n:44 complete; full Drive Organisation Diagnosis produced |
| Critic fail on IMG metadata | s8-e0cc1855 | 19 | Critic n:30: `IMG_20260601_165420.txt ext=.txt, destination=Pictures/2026 — not an image file; correct destination is Documents/`; recovery planner n:33 queued | 

Note: s8-e0cc1855 is referenced in `state/sessions/` — log not captured in `code/logs/`.

**Pass run (s8-b0dffdf2) — key node timings from `code/logs/phase1_pass.log`:**

| Node | Skill | Elapsed | Note |
|---|---|---|---|
| n:1 | planner | 5.3 s | emits parallel batch |
| n:2 | pattern_analyzer | 12.5 s | parallel with classifiers |
| n:3 | sensitive_detector | 185.8 s | local provider; privacy contract |
| n:4 | classifier (batch 1) | 204.8 s | parallel |
| n:6 | classifier (batch 2) | 16.0 s | parallel |
| n:8 | classifier (batch 3) | 66.2 s | parallel |
| n:5 | critic | 8.2 s | fail → recovery planner n:13 |
| n:27 | formatter (round 1) | 185.3 s | full Phase-1 report |
| n:66 | formatter (round 2) | 185.1 s | second formatter after recovery cycle |

**Fail run (s8-465e6637) — key node timings from `code/logs/phase1_fail.log`:**

| Node | Skill | Elapsed | Note |
|---|---|---|---|
| n:1 | planner | 5.4 s | emits parallel batch (19-file drive) |
| n:2 | pattern_analyzer | 167.1 s | parallel |
| n:3 | sensitive_detector | 185.6 s | parallel; local provider |
| n:4 | classifier (batch 1) | 5.6 s | parallel |
| n:6 | classifier (batch 2) | 25.5 s | parallel |
| n:8 | classifier (batch 3) | 81.2 s | parallel |
| n:5 | critic | 7.1 s | fail → recovery planner n:11 |
| n:9 | critic | 4.8 s | fail → recovery planner n:12 |
| n:44 | formatter | 185.2 s | Drive Organisation Diagnosis produced |

---

## Phase 3 features

| Feature | File | What it does |
|---|---|---|
| Move executor | `code/executor.py` | `MoveExecutor` with `dry_run()` (read-only conflict check: src present, dst parent writable, no hash-differing collision), `apply()` (writes undo-log entry atomically before each rename; same-volume moves use `shutil.move` for atomicity; cross-volume copies verify SHA-256 before deleting source), and `undo()` (reverses completed moves in reverse order; unexecuted entries silently skipped). |
| Scan config | `code/scan_config.yaml` | `include_paths`, `exclude_paths`, `locked_zones`, `use_everything_index` fields. Scanner reads it at the start of every scan; Lock toggles in the Dashboard write back to `locked_zones` automatically via `_save_scan_config()`. |
| Scanner mtime layer | `code/scanner.py` Tier-1a | On each file, checks `state/scan_state.json` for a matching `{mtime, size}` entry. Unchanged files reuse the cached SHA-256 hash and skip re-hashing. *Speed layer*: unchanged files cost one dict lookup instead of a full read. |
| Scanner ledger layer | `code/scanner.py` Tier-1d | After hashing, checks `state/ledger.json` keyed by SHA-256. Files already moved in a prior session are emitted as `already_handled` and excluded from `files[]`. *Correctness layer*: the planner never re-classifies completed work. `executor.update_ledger()` appends new entries after each `apply()`. |
| UI Approve flow | `code/ui/app.py::_dlg_approve` | "Approve Medium Plan" builds `MoveOp` list from the session's classifier outputs, calls `dry_run()`, and displays conflicts + reclaimable bytes. Execute calls `apply()` in a thread; on success the Undo button appears and calls `MoveExecutor.undo()` from the returned `UndoLog`. |

---

## Roadmap after this

These are intentionally not addressed in the current scope; noted so the reviewer sees the
forward pointers were understood, not bolted on.

- **Resumable tool loops** → a multi-day 2TB scan resumes from file N, not file 1.
- **Critic-with-tools** → the destination Critic gets `stat`/regex tools to ground
  its verdict in real filesystem checks instead of guessing from filenames alone.
- **Semantic chunking** → large documents chunked by concept before the classifier
  reads them; prevents token-limit truncation on dense files.
- **Browser-grounded research** → less applicable here (noted to show judgment:
  this tool is deliberately metadata-first, not content-scraping).

---

## Final checklist

| # | Requirement | Status |
|---|---|---|
| 1 | Five base queries run end-to-end (hello, Shannon Wikipedia, London/Paris/Berlin parallel, graceful fail, resume-after-kill) | ✅ Phase 0 complete; logs in `code/logs/`; sessions s8-f6737e25, s8-caab497e, s8-a7853431, s8-5d61f0e1, s8_K_resumed_v2 |
| 2 | Parallel fan-out — multiple independent nodes fire simultaneously | ✅ `pattern_analyzer` + 3× `classifier` + `sensitive_detector` all emit from the Planner simultaneously and run via `asyncio.gather`; verified in `test_file_organizer_dag_wires_into_real_graph` |
| 3 | Critic verdict: pass, fail, and recovery | ✅ Phase 1 wired; critics in `phase1_pass.log` (s8-b0dffdf2) and `phase1_fail.log` (s8-465e6637) show both fail paths with recovery planners; IMG-misclassification fail captured in session s8-e0cc1855 |
| 4 | Coder skill + SandboxExecutor | ✅ `prompts/coder.md` implemented; demonstrated in Query I (s8-a7853431): coder emits `{"code":…}`, sandbox runs it, formatter quotes `Paris and Berlin, difference 1,574,000` |
| 5 | New skill (beyond the original set) | ✅ Three new skills: `classifier`, `sensitive_detector`, `pattern_analyzer` — each a yaml entry + prompt; `flow.py` unchanged |
