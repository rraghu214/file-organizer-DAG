# What's new vs the original Session8StartingCode

This is your baseline: the original Session 8 starting code with the
file-organiser additions merged in. Start from HANDOFF.md.

## Modified (replaced original)
- `S8SharedCode/code/prompts/coder.md` — stub filled (assignment req 4).
- `S8SharedCode/code/prompts/planner.md` — extended with file-organiser triage rules.
- `S8SharedCode/code/agent_config.yaml` — 3 new skills appended at the bottom.
- `S8SharedCode/gateway/agent_routing.yaml` — sensitive_detector + classifier pinned local (privacy).

## Added (new files)
- `S8SharedCode/code/prompts/classifier.md`
- `S8SharedCode/code/prompts/sensitive_detector.md`
- `S8SharedCode/code/prompts/pattern_analyzer.md`
- `S8SharedCode/code/scanner.py` — Tier-0/Tier-1 cheap index.
- `S8SharedCode/code/tests/test_file_organizer.py` — 6 new tests.
- `S8SharedCode/demo_messy_drive/` — ~22-file demo drive.
- `HANDOFF.md` — full context + phased task list. READ THIS FIRST.
- `README_FileOrganiser.md` — the product/assignment README.

## Untouched from original
flow.py, schemas.py, recovery.py, persistence.py, sandbox.py,
mcp_runner.py, memory.py, artifacts.py, vector_index.py, replay.py,
gateway.py, tests/test_recovery.py.

Note: skills.py was modified in Phase 0 (parse_skill_json strict=False,
render_prompt INPUTS cap 8k, _format_memory_hits source filter) and again
in Phase 1 (prompt_template UTF-8 encoding, render_prompt skips INPUTS
for USER_QUERY-only prompts). It is no longer "untouched from original".

## Verify
    cd code && .venv\Scripts\python.exe -m pytest tests/ -q     # 28 pass

---

## Phase 0 live-run fixes (2026-05-31)

These were discovered during the first live run against `demo_messy_drive`.
All are prompt-edits or a one-line infrastructure fix; `flow.py` untouched.

### Fix 1 — `parse_skill_json`: add `strict=False` (`skills.py`)
**Symptom**: formatter, coder, pattern_analyzer all returned `output: {}`
despite Gemini responding with 100-1400 chars of content.
**Root cause**: Gemini 2.5 Flash writes actual newline characters inside
JSON string values (`final_answer`, `code`, plan text) instead of the `\n`
escape sequence. Python's `json.loads` (strict mode by default) rejects
control characters inside strings and raises `JSONDecodeError`, causing
`parse_skill_json` to silently return `{}`.
**Fix**: pass `strict=False` to every `json.loads` call in
`parse_skill_json`. Valid strict JSON parses identically; only multi-line
string values are now tolerated. One-line change, two call sites.

### Fix 2 — `planner.md`: ignore `user_query` memory hits
**Symptom**: after a failed run the query itself was stored as a memory
`fact`. On the next run the planner saw it as a "prior answer" and
returned `{}` with no nodes.
**Fix**: added a rule distinguishing hits with `source: user_query`
(stored queries, not answers) from hits with other sources.

### Added — `run_organiser.py`
Thin launcher: runs `scanner.scan()` → embeds JSON in query → calls
`Executor().run()`. Needed because passing large JSON through a PowerShell
argument is unreliable. Not part of the engine; purely a dev convenience.

### Fix 3 — `persistence.py`: UTF-8 encoding on Windows
**Symptom**: `UnicodeEncodeError: 'charmap' codec can't encode character '‑'`
— groq's model used a non-breaking hyphen in its rationale; `_atomic_write`
opened the file with the default Windows encoding (cp1252) which can't encode it.
The process crashed with a 0-byte `.tmp` file and the node state was never updated.
**Fix**: pass `encoding="utf-8"` (or `None` for binary) to every `open()` call
in `_atomic_write`. One-line change.

### Fix 4 — `gateway/main.py`: soft pin instead of hard pin
**Symptom**: when 5 skills were all pinned to the same provider (cerebras/groq)
and that provider returned 429, the gateway returned an immediate 502 — no
failover. This killed parallel nodes instantly instead of routing around the limit.
**Root cause**: agent routing set `explicit_override=True`, which tells the
failover loop "this is a caller-specified pin — don't retry other providers."
**Fix**: agent routing now stores the preference in `_agent_preferred` and
reorders the candidate list (preferred provider first, full failover chain after)
WITHOUT setting `explicit_override`. A 429 on the preferred provider now falls
over to the next available provider automatically.
**Bonus**: concurrent parallel calls naturally land on different providers because
each 429 puts the first provider into cooldown before the next call picks.

### Fix 5 — `agent_routing.yaml`: spread parallel skills across providers
Each distinct skill type in the file-organiser plan is soft-pinned to a DIFFERENT
starting provider so 5 concurrent calls hit 5 different providers from t=0:
  classifier → cerebras, sensitive_detector → nvidia, pattern_analyzer → gemini,
  formatter → nvidia (100k context; handles the large combined upstream prompt),
  planner / critic → groq, coder → groq.

### Fix 6 — `agent_config.yaml`: raise max_tokens for multi-line outputs
`formatter` 1500→4000, `classifier` 1500→2500, `coder` 1500→2500.
**Root cause**: cerebras/groq models hit the token cap mid-JSON, producing
truncated output that parse_skill_json could not extract → silent `{}`.

### Fix 7 — `skills.py render_prompt`: reduce INPUTS to 8 000 chars
The formatter receives ALL upstream outputs concatenated. With 5 upstream nodes
each returning ~4 000 chars, the prompt hit 21 000 chars (9 000+ tokens) —
exceeding cerebras (8k) and github (8k) context limits and exhausting groq TPM.
Reducing the INPUTS cap from 20 000 to 8 000 chars keeps the formatter prompt
under 10 000 chars, within every provider's context window.

### Fix 8 — `planner.md`: skip coder when SCAN_RESULT has duplicate_groups
**Symptom**: planner always emitted a `coder` node; coder produced `{}` (no
`code` field); sandbox_executor failed; recovery planner fired; new coder produced
`{}`; infinite recovery loop until the 60-node cap hit.
**Root cause**: the scanner already pre-computes `duplicate_groups` — nothing
needs to be coded. The coder was solving a solved problem.
**Fix**: one sentence in planner.md: "If `duplicate_groups` is present in
SCAN_RESULT, the scanner already computed dedup — do NOT emit coder."

### Noted — provider fleet usage for the file-organiser demo
`gemma4:e4b` (9.6 GB, ollama) is too slow for concurrent calls. Cloud providers
handle the parallel fan-out in 5–15 s per skill. In production, swap
sensitive_detector and classifier back to `ollama` with a smaller model:
  `ollama pull llama3.2:3b`  (2 GB, ~3 s/call, no concurrency timeout risk)

---

## Phase 1 live-run fixes (2026-06-04)

Discovered while wiring the critic on the classifier→formatter edge (req 3).

### Fix 1 — `skills.py prompt_template`: read prompts as UTF-8
**Symptom**: UnicodeDecodeError 'charmap' codec can't decode byte 0x90 — any
prompt file containing non-ASCII characters (e.g. box-drawing chars `═`) crashed
on Windows where the default encoding is cp1252.
**Fix**: pass `encoding="utf-8"` to `self.prompt_path.read_text()`.

### Fix 2 — `skills.py render_prompt`: skip INPUTS for USER_QUERY-only skills
**Symptom**: Planner and classifiers silently returned `{}` on cerebras/gemini.
Prompt was ~19 000 chars because the full SCAN_RESULT (6 500 chars) appeared twice:
once in the `USER_QUERY:` header and again JSON-encoded in `INPUTS:`.
**Fix**: when every resolved input is USER_QUERY (no upstream `n:xxx` outputs),
skip the INPUTS block entirely. The full query is already in the USER_QUERY header;
re-encoding it in INPUTS just doubled the prompt and exceeded smaller context windows.

### Fix 3 — `code/agent_config.yaml`: critic max_tokens 500→800
**Symptom**: critics returned `{}` when processing 18-item classified lists —
800 tokens isn't large but it's enough headroom for a one-sentence verdict.

### Fix 4 — `code/prompts/critic.md`: PRIORITY RULE for classifier checks
**Symptom**: critics returned `{}` (no verdict) even when the classified list
clearly contained a `.txt` file routed to `Pictures/`. Root causes: (a) the
file-organiser check was buried at the end of the prompt after the general
fabrication/contradiction check; (b) `UPSTREAM_OUTPUT` was referenced but no
section by that name exists — models had to guess the mapping to `INPUTS[0].output`.
**Fix**: complete rewrite putting a PRIORITY RULE first with explicit
`INPUTS[0].output.classified` reference; Step A catches empty classifier output,
Step B scans for `.txt-in-Pictures` mismatch and cross-references `preview` from
SCAN_RESULT in USER_QUERY. PHOTO-* placeholder stubs are the documented exception.
FALLBACK general check preserved for distiller / format critic use cases.

### Fix 5 — `code/prompts/planner.md`: formatter must list BOTH classifier AND critic labels
**Symptom**: formatter received only critic verdicts (`{"verdict":"pass"}`) as inputs,
not the actual classified file lists. The planner was following a contradictory instruction
("formatter must list the CRITIC labels, not the classifier labels") that overrode the
example DAG which correctly showed both.
**Fix**: updated the instruction to say "list BOTH the classifier label AND its critic
label — classifiers supply the actual file data; critics act as gates."

### Fix 6 — `demo_messy_drive/Downloads/IMG_20260601_165420.txt` (new file)
Deliberately-misclassified file demonstrating the critic fail case:
- Name: `IMG_20260601_165420.txt` (classic phone-photo naming convention)
- Content: 954-byte sprint meeting notes (>600 B threshold, so scanner emits NO preview)
- Classifier sees IMG_YYYYMMDD name only → routes to `Pictures/2026` (misclassification)
- Critic Step B fires: ext=.txt, no preview, destination=Pictures/ → `verdict:fail`
- Recovery planner receives: "correct destination is Documents/"
Evidence: session s8-e0cc1855, node n_030.json in state/sessions.

---

## Phase 2 NiceGUI app (2026-06-04)

New files — all in `code/`:

### `ui/session.py`
Data layer. `list_sessions()` sorts by hex timestamp; `load_session(sid)` reads
`query.txt` + `graph.json` + `nodes/n_*.json`. Extractors: `classified_items` (merges all
classifier outputs, deduplicates by name+destination), `sensitive_files`, `pattern_analysis`,
`formatter_output`, `group_by_destination`, `session_stats`.
Key quirk: classifier `result.output` may arrive as a raw JSON array (not wrapped in a dict)
— `classified_items` handles both forms with `isinstance(out, list)`.

### `ui/dag_svg.py`
Pure-Python SVG string builder (no NiceGUI dependency). Algorithm: longest-path-from-source
layering via memo-recursive DFS; nodes sorted by metadata.label within each layer for stable
column order. Skill colours encoded as hex; status icons (✓ ✗ ⊘ ⟳ ○) in node labels.
Output wrapped in `overflow-x:auto` in the dashboard for sessions with many recovery nodes.

### `ui/widgets.py`
Reusable NiceGUI micro-components: `stat_card`, `conf_bar` (linear_progress + percentage),
`file_row` (one file inside a destination expansion), `section_header`.

### `ui/app.py`
Four tabs: Dashboard, Compare Plans, Filter Files, History.
- Dashboard: summary cards → DAG SVG → highlights with Lock switches → destination groups
  with confidence bars and "needs your eyes" badges → private panel → dup groups → skipped.
- Compare Plans: three columns (minimal/medium/best) + cumulative diff showing what each
  tier adds over the previous.
- Filter Files: three-tier — structured (category/destination/confidence slider),
  semantic combobox, NL plain-language box (keyword match in-process, no LLM round-trip).
- History: session list with node count + formatter-complete status.
- Action dialogs: Approve (Phase 3 stub), Refine (spawns `run_organiser.py` subprocess
  with refinement note prepended), Help me choose (in-process Q&A).
NiceGUI event fix: `on_change=` used for `ui.select` and `ui.switch` to get
`ValueChangeEventArguments` (.value); raw `.on()` would give `GenericEventArguments` (.args).

### `code/run_ui.py`
Launcher: inserts `code/` into sys.path so package-relative imports in `ui/` work when
invoked as `python run_ui.py` (running `ui/app.py` directly fails with relative-import error).
