# Session 8 — File Organiser Agent (DAG build)

A privacy-aware, agentic file-organisation tool built on the Session 8
multi-agent DAG orchestrator. It scans a messy folder, diagnoses its
organisation, fans out classification across independent file batches in
parallel, quarantines private files **without ever reading their content**,
computes duplicates/space with real Python execution, and produces a
phase-1 report the user refines before any phase-2 move happens.

This README maps the build to the five assignment requirements and shows
how to run the sub-minute demo.

---

## Why a DAG (the S7 → S8 story)

A messy folder is a set of *independent* decisions: classifying the docs
does not depend on classifying the photos. Under the S7 single loop those
decisions serialise. Under the S8 DAG they fan out through
`asyncio.gather`. The architecture is load-bearing, not decorative.

A second reason: cost. Following the **Everything** file-search
methodology (read cheap metadata first, escalate only what needs
judgment), the tool runs three tiers — structural scan, then cheap
signals (hash dedup, folder short-circuit, sensitive prefilter), then the
expensive LLM tier *only on what survives*. `scanner.py` is tiers 0–1;
the `classifier` / `pattern_analyzer` nodes are tier 2.

---

## What was added (no `flow.py` change)

Everything below is a yaml entry + a prompt file + one pure-Python helper.
The orchestrator was not modified — proven by
`tests/test_file_organizer.py::test_no_orchestrator_modification_needed`.

| File | What it is |
|---|---|
| `prompts/coder.md` | **Filled the stub** (req 4). Emits stdlib Python that computes/verifies an answer; routes to `sandbox_executor`. |
| `prompts/classifier.md` | New skill — categorises a batch of non-sensitive files with confidence + `needs_review`. |
| `prompts/sensitive_detector.md` | New skill — flags private files from **metadata only**; `content_read` is always false. |
| `prompts/pattern_analyzer.md` | New skill (req 5) — diagnoses folder state, leads with **highlights** of well-organised zones, emits **minimal / medium / best** plans. |
| `prompts/planner.md` | Extended with file-organiser triage rules (parallel fan-out + privacy split). |
| `agent_config.yaml` | Three new skill entries appended. |
| `scanner.py` | Tier-0/Tier-1 cheap index: scandir walk, SHA-256 dedup, folder short-circuit, metadata-only sensitive prefilter. |
| `gateway/agent_routing.yaml` | `sensitive_detector` + `classifier` pinned to **local ollama** so file data never reaches the cloud. |
| `tests/test_file_organizer.py` | 6 tests covering the scanner and the DAG wiring. |

---

## Requirement-by-requirement

**1 — Five base queries.** The original engine is byte-unchanged, so
`hello / A / I / J / K` run exactly as in the session. Logs go in
`logs/`.

**2 — Parallel fan-out.** A cleanup query makes the Planner emit
`pattern_analyzer` + two `classifier` nodes + one `sensitive_detector`,
all with the (complete) Planner as their only predecessor — so all four
are `ready` at once and run concurrently. The Formatter waits on all four
(the `asyncio.gather` barrier). Verified by
`test_file_organizer_dag_wires_into_real_graph`: the three analysis skills
are simultaneously ready and the formatter has exactly four predecessors.

**3 — Critic verdict (pass and fail).** The `classifier` emits a proposed
`destination` per file. A `critic` node verifies the destination matches
the file's category. *Pass*: a clean tax invoice → `Finance/Receipts/2026`
is approved. *Fail*: feed a misclassified file (e.g. a `.txt` that is
actually a photo dump routed to `Documents/`) → Critic returns `fail` →
the orchestrator splices a recovery Planner (the splice mechanics are the
ones already pinned by `tests/test_recovery.py`).

**4 — Coder skill.** `prompts/coder.md` is implemented. Demonstrated on a
dedup/size query: the Coder emits Python that SHA-256-hashes the file
manifest and prints the duplicate groups and reclaimable bytes; the
SandboxExecutor runs it and the Formatter quotes the exact integer. The
worked example in the prompt was executed through the real `sandbox.py`
and produces `Paris and Berlin, difference 1,574,000`.

**5 — New skill.** `pattern_analyzer` (plus `classifier`,
`sensitive_detector`). One yaml entry + one prompt each; the orchestrator
needed no change.

**6 — YouTube demo / 7 — this README with logs.** Demo script below.

---

## The privacy boundary (the product's centrepiece)

Files matching sensitive signals (salary, statement, bank, PAN, Form16,
`.kdbx`, …) are caught by `scanner.py`'s metadata-only prefilter and routed
to `sensitive_detector`, which is **pinned to a local provider** in
`agent_routing.yaml`. Their content is never read and never leaves the
machine. The detector still returns a *judgmental call with a confidence
%* and a suggested destination — derived from filename/path/size alone,
with `content_read: false` always. Hashing for dedup is still applied
(it is not semantic content reading).

---

## Run the demo (sub-minute)

```bash
# 0. prerequisites: build llm_gatewayV8, set provider keys in .env.
#    For the privacy pins, configure an ollama provider (e.g. gemma);
#    or temporarily change the two pins in gateway/agent_routing.yaml to
#    `groq` to run without ollama (note: privacy property only holds local).

cd S8SharedCode/code

# 1. cheap-tier scan of the demo drive (no LLM, milliseconds)
python scanner.py ../demo_messy_drive

# 2. run the organiser query through the DAG
python flow.py "Analyse and organise the folder at ../demo_messy_drive: \
group receipts and photos, flag anything private, find duplicates, \
and tell me how well it's organised with effort options."

# 3. resume demo (req shows persistence): kill step 2 mid-run with Ctrl-C, then
python flow.py --resume <session_id>

# 4. tests
python -m pytest tests/ -q     # 28 pass (22 original + 6 new)
```

The demo drive (`demo_messy_drive/`, ~22 files) is built to hit every
requirement in one run: a well-organised `Projects/` zone (→ highlight),
scattered receipts (→ classifier + group-by-year), a duplicate photo pair
(→ Coder dedup), four private files (→ sensitive_detector, never read), an
installer-extract folder (→ folder short-circuit), and stale downloads
(→ archive suggestion).

---

## Honest scope

This is the **assignment** (the engine + a small demo drive). The
**product** — recursive 2TB scanning, the Everything-SDK fast index on
Windows, the all-Python NiceGUI front end reading `state/sessions/<sid>/`,
the transactional move-executor with undo, the processed-ledger that skips
already-handled files on re-scan, and lockable well-organised zones — is
the roadmap, deliberately out of scope here.

### Session 9 forward pointers (not in this assignment)
- **Resumable tool loops** → a multi-day 2TB scan resumes from file N, not file 1.
- **Critic-with-tools** → the destination Critic gets `stat`/regex tools to ground its verdict in real filesystem checks.
- **Semantic chunking** → large documents chunked by concept before the classifier reads them.
