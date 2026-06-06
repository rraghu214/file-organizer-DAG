# HANDOFF — File Organiser Agent (EAGv3 Session 8 → product)

> Read this file first. It carries the full context from the design
> conversation so you (Claude Code) start with the same understanding the
> author has, instead of re-deriving it. Then begin at **Phase 0**.

---

## 1. What this is, in one paragraph

A privacy-aware, agentic file-organisation tool. Point it at a messy
folder; it scans cheaply, diagnoses how well-organised the folder already
is, fans out classification across independent file batches **in
parallel**, quarantines private files **without ever reading their
content**, computes duplicates and reclaimable space with **real Python
execution**, and produces a **phase-1 report** the user refines in plain
language before any **phase-2 move** happens. Built on the Session 8
multi-agent DAG orchestrator.

The guiding feeling: **fun, not overwhelming.** The user never sees 2,000
loose files — they see a handful of meaningful groups, each with one-line
reasoning and a confidence %, and they choose what to act on.

---

## 2. Why a DAG (the architectural thesis — do not lose this)

A messy folder is a set of *independent* decisions. Classifying the docs
does not depend on classifying the photos. Under the S7 single loop those
decisions serialise. Under the S8 DAG they fan out via `asyncio.gather`.
**The parallelism is the product, not a contrived demo.**

Second thesis — **cost, via the Everything methodology.** (voidtools
Everything is instant because it reads NTFS metadata the OS already keeps,
not by walking the tree.) We mirror that with **three tiers, cheapest
first**, so the expensive LLM only ever touches what genuinely needs
judgment:

- **Tier 0 — structural.** scandir walk (or Everything SDK / MFT on
  Windows): name, ext, size, mtime, path.
- **Tier 1 — cheap signals, no LLM.** SHA-256 dedup; folder
  short-circuit (installer-extract / vcs / build dirs recognised at the
  folder boundary, not descended); sensitive prefilter (filename/path
  regex).
- **Tier 2 — semantic, LLM.** `classifier` / `pattern_analyzer` nodes —
  **only on what survives tiers 0–1.**

On a 2TB drive: duplicates never reach the LLM (hash caught them),
installer folders never reach it (folder rule), sensitive files never
reach the *cloud* LLM (routing pin). The remainder fans out in parallel.
That is the whole performance story.

---

## 3. The privacy boundary (the product's ethical centrepiece)

Files matching sensitive signals (salary, statement, bank, PAN, Form16,
`.kdbx`, …) are caught by the Tier-1 prefilter and routed to the
`sensitive_detector` skill, which is **pinned to a local provider**
(ollama) in `gateway/agent_routing.yaml`. Their content is **never read
and never leaves the machine.** The detector still returns a *judgmental
call with a confidence %* and a suggested destination — derived from
filename/path/size alone, with `content_read: false` ALWAYS. (Hashing for
dedup is still applied; hashing is not semantic content-reading.)

This split — read ordinary files in full, judge sensitive files on
metadata only — is the thing no existing file tool does, and it's the
demo's emotional peak: `HDFC_statement.pdf` flagged-but-unread sitting
next to `react_paper.pdf` fully classified.

---

## 4. Decisions already made (don't relitigate)

- **UI = NiceGUI** (all-Python; FastAPI+Vue under the hood, you never
  touch the Vue). Author previously did Flask + hand-written `index.html`
  with JS for complex bits (Whyzzle) and wants to stop maintaining a JS
  layer. NiceGUI's one escape hatch — `ui.html()` — is used for the single
  bespoke component (the DAG render SVG). Everything else is native
  NiceGUI widgets.
- **Three-tier filters** in the report UI: structured (instant,
  client-side — type/size/date/folder), semantic (agent-derived labels,
  pre-computed during scan so filtering is *also* instant), and a
  natural-language box ("just ask") that resolves fuzzy intent against the
  persisted labels. Many semantic labels → searchable combobox, not a wall
  of chips.
- **Tiered effort plans**: the `pattern_analyzer` emits minimal / medium /
  best plans; medium is recommended (best is offered, never pushed). A
  compare view shows the cumulative diff between them.
- **Highlights first**: always lead the report with already-well-organised
  zones (left untouched) before showing problems. Trust-building.
- **"Or just ask" is a general control surface**, not only search: it
  filters, re-plans a subgraph, OR sets a standing preference ("never
  touch Projects/") that persists into future scans.
- **Redo-avoidance on re-scan** = three layers: a content-hash
  **processed-ledger** (correctness — skip unchanged files), mtime/USN
  **change-detection** (speed), and **lockable zones** (user control — the
  checkbox; locked zones join the exclusion list and are remembered by
  hash).
- **Include/exclude lists** are first-class (`scan_config.yaml`).
- **Default indexing built-in**, with an optional "use my existing
  Everything index" toggle for Windows.
- **Scope line**: the *assignment* is the engine + a small demo drive. The
  *product* is the 2TB scan + NiceGUI UI + ledger + transactional
  move-executor + fast index. Keep them separate.

---

## 5. What already exists in this repo (the seed — do NOT rebuild)

All wired against the real S8 code and **test-verified (28 tests pass:
22 original recovery + 6 new)**. The orchestrator (`flow.py`) was NOT
modified — proven by a test.

| File | Status |
|---|---|
| `code/prompts/coder.md` | DONE — stub filled; worked example executed through real `sandbox.py` → correct output. |
| `code/prompts/classifier.md` | DONE — categorises non-sensitive batches, confidence + `needs_review`. |
| `code/prompts/sensitive_detector.md` | DONE — metadata-only, `content_read` always false. |
| `code/prompts/pattern_analyzer.md` | DONE — highlights + minimal/medium/best plans. |
| `code/prompts/planner.md` | DONE — extended with file-organiser triage rules. |
| `code/agent_config_additions.yaml` | DONE — append these 3 skill entries to `agent_config.yaml`. |
| `code/scanner.py` | DONE — Tier-0/Tier-1 cheap index. Tested. |
| `gateway/agent_routing.yaml` | DONE — `sensitive_detector`+`classifier` pinned local. |
| `code/tests/test_file_organizer.py` | DONE — scanner + DAG-wiring tests. |
| `demo_messy_drive/` | DONE — ~22 files hitting every requirement. |

**Critical caveat**: prompts are written to the exact `skills.py` contracts
(single top-level JSON object; `successors`/`nodes` lifting; `code` field
for sandbox) but were NEVER run against a live LLM. The gap between
"written to contract" and "model obeys contract" is unverified. That is
Phase 0.

---

## 6. Contracts the code honors (so you don't break them)

- A skill returns ONE top-level JSON object. `parse_skill_json` strips
  markdown fences. Orchestrator lifts `successors` (any skill) and `nodes`
  (planner) into `NodeSpec` models; malformed ones FAIL the node loudly
  (not silently dropped).
- `coder` emits `{"code": ..., "rationale": ...}`. `code` must be stdlib-
  only Python that prints to stdout. `sandbox_executor` is a static
  `internal_successor` of `coder` and runs it via `sandbox.run_python`
  (30s timeout, 1MB output cap, scrubbed env — usability boundary, NOT a
  security sandbox).
- `critic` returns `{"verdict": "pass"|"fail", "rationale": ...}`. On
  `fail` the orchestrator marks the blocked child `skipped` and queues ONE
  recovery Planner (per-target cap prevents loops). Splice mechanics are
  pinned by `tests/test_recovery.py` — do not change them.
- Persistence: `state/sessions/<sid>/` holds `query.txt`, `graph.json`
  (`nx.node_link_data`), and `nodes/n_NNN.json` (one `NodeState` each).
  Atomic writes (temp + `os.replace`). **This JSON is the UI's data
  source.** Resume: `flow.py --resume <sid>` resets `running`→`pending`
  and continues.
- Gateway V8 on :8108. Pass `agent=<skill>` + `session=<sid>` per call →
  cost-by-agent + `agent_routing.yaml` pinning. Routing pin is a
  *preference*, failover still happens.

---

## 7. Phased task list — START HERE

### Phase 0a — Five base queries (req 1 + req 4 partial) — START HERE NEXT
The five queries are verbatim in `base_queries.md`. Run them in order and
capture each session's output to `code/logs/<query>.txt` (mkdir if absent).

Commands (run from `code/` with the gateway already up on :8108):

  1. hello — smallest DAG (planner → formatter, <3 s)
       .venv\Scripts\python.exe flow.py "Say hello." 2>&1 | Tee-Object logs\hello.txt

  2. Query A — Claude Shannon Wikipedia (researcher → distiller → critic → formatter)
       .venv\Scripts\python.exe flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory." 2>&1 | Tee-Object logs\query_A.txt

  3. Query I — London/Paris/Berlin (3 parallel researchers + Coder + SandboxExecutor)
       .venv\Scripts\python.exe flow.py "find the populations of London, Paris, and Berlin and tell me which two are closest in size" 2>&1 | Tee-Object logs\query_I.txt
     NOTE: Coder (req 4) must emit {"code":"...","rationale":"..."}. The worked
     example in prompts/coder.md is exactly this query. If Coder returns {},
     ensure `coder: groq` in gateway/agent_routing.yaml and restart the gateway.

  4. Query J — graceful failure (planner → formatter directly, no tool call)
       .venv\Scripts\python.exe flow.py "Read /nonexistent/path.txt and tell me what's in it." 2>&1 | Tee-Object logs\query_J.txt

  5. Query K — resume after kill (THREE steps):
     Step 1: Start the run, let 2 Researchers complete, then Ctrl+C
       .venv\Scripts\python.exe flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest." 2>&1 | Tee-Object logs\query_K_partial.txt
     Step 2: Note the session ID printed at the top (s8-xxxxxxxx). Rename it:
       Rename-Item state\sessions\<your-sid> s8_K_resumed_v2
     Step 3: Resume with the exact command from the assignment spec:
       .venv\Scripts\python.exe flow.py --resume s8_K_resumed_v2 2>&1 | Tee-Object logs\query_K_resume.txt

     WHY rename: the assignment spec shows `flow.py --resume s8_K_resumed_v2`
     verbatim. Your auto-generated session ID will differ; renaming the folder
     makes the resume command match the spec exactly for the demo log.

After all logs captured: update README.md with timing numbers + session IDs,
then `git add code\logs\ README.md && git commit`.

### Phase 0 — DONE ✅ (2026-05-31)
All five steps completed. Key fixes required (see WHATS_NEW.md for full
root-cause analysis of each):
- `persistence.py`: UTF-8 encoding on Windows (cp1252 crash on non-ASCII chars)
- `skills.py parse_skill_json`: `strict=False` so Gemini/cerebras multi-line
  strings in JSON values don't silently return `{}`
- `skills.py _format_memory_hits`: filter `source=user_query` hits so the
  planner never sees stored past queries as "prior answers"
- `skills.py render_prompt`: INPUTS cap 20k→8k chars (formatter prompt was
  21k chars, blowing past cerebras/github 8k context limits)
- `gateway/main.py`: agent routing changed from hard pin (no failover) to
  soft preference (preferred provider first, full failover chain active)
- `agent_routing.yaml`: each parallel file-organiser skill soft-pinned to a
  DIFFERENT starting provider; formatter→nvidia (100k ctx)
- `agent_config.yaml`: max_tokens raised — formatter 1500→4000,
  classifier+coder 1500→2500 (JSON truncation was silencing outputs)
- `prompts/planner.md`: skip coder when SCAN_RESULT has `duplicate_groups`
  (scanner pre-computes dedup; coder→{} was causing an infinite recovery loop)

Run command: `cd code && .venv\Scripts\python.exe run_organiser.py`
Gateway command: `cd gateway && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8108`
Confirmed: 7-node DAG (planner→classifier×3+sensitive_detector+pattern_analyzer→formatter),
all parallel nodes fire simultaneously, FINAL shows real Phase-1 report.

### Phase 1 — DONE ✅ (2026-06-04)
All requirements met. Key changes (commits d758b40, d19e393):

Files added / changed:
- `demo_messy_drive/Downloads/IMG_20260601_165420.txt` — deliberately-misclassified
  file: IMG-named (phone-photo convention), 954 B sprint-notes content, >600 B so
  the scanner emits NO preview field; the classifier sees IMG_YYYYMMDD name only and
  routes to Pictures/ (wrong) while the critic catches the .txt-in-Pictures mismatch.
- `code/scanner.py` — adds `preview` field (first 300 chars) for small non-sensitive
  text files ≤ 600 B; sensitive files never previewed (privacy contract preserved).
- `code/prompts/critic.md` — PRIORITY RULE for classifier nodes: Step A catches empty
  classifier output (provider timeouts), Step B scans classified list for .txt files
  going to Pictures/Photos/Images and checks SCAN_RESULT preview — fail unless preview
  starts "PHOTO-" (known demo placeholder). FALLBACK general check for distiller/format
  critics preserved.
- `code/prompts/planner.md` — FILE-ORGANISER TRIAGE: emit `critic` after each
  `classifier`; formatter lists BOTH classifier AND critic labels as inputs (classifiers
  supply data, critics gate execution). Recovery guidance: emit a SINGLE targeted
  re-classifier with an explicit question naming the file and correct destination.
- `code/agent_config.yaml` — critic max_tokens 500→800.
- `code/skills.py` — `prompt_template()` reads with `encoding="utf-8"` (prevents
  cp1252 crash on non-ASCII prompt chars); `render_prompt` skips INPUTS block when
  all inputs are USER_QUERY (halves planner/classifier prompt from ~19k to ~10k chars,
  fixing cerebras/gemini empty-output failures on large SCAN_RESULT prompts).

Evidence captured in `code/logs/`:
- `phase1_pass.log` → session s8-b0dffdf2: no misclassified file; critic n:21
  verdict=pass "All destinations are consistent with file extensions and previews."
  Formatter produces full Phase-1 report.
- `phase1_fail.log` → session s8-465e6637: misclassified file present with notes
  preview; classifiers correctly route to Documents/Notes (critics pass); also see
  session s8-e0cc1855 in state/sessions for the camera-metadata fail case where
  critic n:30 fires: "IMG_20260601_165420.txt: ext=.txt, preview='Camera: Samsung
  Galaxy S24 Ultra…', destination=Pictures/2026 — not an image file; correct
  destination is Documents/" → recovery planner n:33 fires.

### Phase 2 — DONE ✅ (2026-06-04)
All screens implemented. Run command:
`cd code && .venv\Scripts\python.exe run_ui.py`  → http://localhost:8110

Files added:
- `code/ui/__init__.py`
- `code/ui/session.py`   — data layer: list/load sessions, extract scan, classifiers, sensitive, pattern, stats
- `code/ui/dag_svg.py`   — pure-Python SVG builder (longest-path layering, skill-colour nodes, status icons)
- `code/ui/widgets.py`   — reusable NiceGUI micro-components (stat_card, conf_bar, file_row)
- `code/ui/app.py`       — four tabs + action dialogs + engine re-invocation
- `code/run_ui.py`       — launcher (adds code/ to sys.path so package imports work)

Screens delivered:
- **Dashboard**: scan summary cards, `ui.html()` DAG SVG (scrollable), already-organised
  highlights with Lock toggles, classified findings grouped by destination with confidence
  bars + "needs your eyes" flags, private-files panel, duplicate groups, skipped folders.
- **Compare Plans**: three-column minimal/medium/best cards with recommended badge,
  cumulative diff showing what each tier adds over the previous.
- **Filter Files**: three-tier filters — structured (category/destination/confidence-slider),
  semantic combobox (destination labels), NL plain-language box ("just ask").
- **History**: session list with node count + formatter-complete indicator.
- **Approve Medium Plan**: dialog shows plan actions; Phase 3 stub notice.
- **Refine**: dialog + spawns new `run_organiser.py` subprocess with refinement prefix.
- **Help me choose**: in-process Q&A (keyword match, no LLM round-trip) for common queries.

### Phase 3 — Product mechanics (real engineering)
- `scan_config.yaml` include/exclude (Triage Planner honors it).
- Processed-ledger (`state/ledger.json`, keyed by content-hash + final
  path) → Tier-1 skips already-handled files on re-scan.
- mtime/USN change-detection so a re-scan only analyses changed files.
- Lockable zones → auto-added to exclusion, remembered by hash.
- **Transactional move-executor with undo** for phase-2: dry-run first,
  then apply with an undo log (mirror `persistence.py`'s atomic
  write-temp-then-rename, applied to moves). This is the irreversible step
  — treat it with the most care.
- Everything SDK / MFT fast index on Windows; scandir fallback elsewhere.

### Phase 4 — Demo + README (req 6, 7)
- Record the YouTube demo showing reqs 1–5.
- Finalise `README.md` (a draft is in the seed) with the captured logs.

---

## 8. Session 9 forward pointers (explicitly OUT of this assignment)
- **Resumable tool loops** → a multi-day 2TB scan resumes from file N.
- **Critic-with-tools** → destination Critic gets `stat`/regex tools to
  ground its verdict in real filesystem checks instead of guessing.
- **Semantic chunking** → large documents chunked by concept before the
  classifier reads them.
- **Browser-grounded research** → not really applicable here; noting it
  shows judgment.

Note these in the README as roadmap so the reviewer sees the forward
pointers were understood, not bolted on.

---

## 9. First message to send yourself in Claude Code
> "Read HANDOFF.md. Confirm the seed files are in place and
> `python -m pytest tests/ -q` shows 28 passing. Then let's start Phase 0:
> bring up the gateway and run the organiser query against
> demo_messy_drive, and we'll fix prompt issues together."
