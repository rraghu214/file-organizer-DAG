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

### Phase 0 — Make it run live (highest value; I could not do this)
1. Drop the seed files into `S8SharedCode/`; append
   `agent_config_additions.yaml` to `agent_config.yaml`.
2. Build/start `llm_gatewayV8`; set provider keys in `.env`. Configure an
   ollama provider for the privacy pins (or temporarily switch the two
   pins to `groq` to run without ollama — but note the privacy property
   only holds local).
3. Run the 5 base queries (`hello, A, I, J, K`) → capture `logs/`
   (assignment req 1 + 7).
4. Run the organiser query against `demo_messy_drive`. Watch the planner
   JSON parse cleanly. Fix prompt issues (expect 2–3 tweaks) — prompt
   edits only, no code changes.
5. Confirm the parallel fan-out in the trace (classifier ×2 +
   sensitive_detector + pattern_analyzer all start together) — req 2.

### Phase 1 — Critic fail case (req 3)
- Add a deliberately-misclassified file (e.g. a photo-dump `.txt` the
  classifier routes to `Documents/`). Insert/confirm a `critic` verifying
  destination-matches-content. Iterate until ONE run passes and ONE run
  fails, the fail splices a recovery Planner, and the recovered answer is
  correct. Capture logs.

### Phase 2 — NiceGUI app (the part the author wants to own)
- Backend: a thin FastAPI/NiceGUI service that reads
  `state/sessions/<sid>/` JSON. No new agent logic.
- Rebuild these screens as NiceGUI components (the design spec is in the
  conversation — report dashboard, group drill-down, compare-plans,
  three-tier filters, locked-zones toggles):
  - report dashboard: scan summary cards, the DAG render (`ui.html()` +
    SVG), grouped findings with confidence bars + "see files & why".
  - drill-down: per-file reasoning + destination + confidence;
    low-confidence flagged "needs your eyes"; "tell me what to select" →
    natural-language selection.
  - compare-plans: cumulative diff table + locked-zones toggles.
  - filters: structured selects + semantic combobox + NL box.
- Wire approve/refine buttons to re-invoke the engine (refine = re-plan
  the affected subgraph only; the persisted graph lets unaffected branches
  stay cached).

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
