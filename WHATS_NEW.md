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
flow.py, skills.py, schemas.py, recovery.py, persistence.py, sandbox.py,
mcp_runner.py, memory.py, artifacts.py, vector_index.py, replay.py,
gateway.py, all other prompts, the whole gateway/ app, tests/test_recovery.py.

## Verify
    cd S8SharedCode/code && python -m pytest tests/ -q     # 28 pass

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
