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

### Noted — ollama serialises concurrent requests
`gemma4:e4b` (9.6 GB) queues concurrent calls: 3 ollama skills
(classifier×2 + sensitive_detector) took 147s + 360s + 583s respectively.
For demo speed, pull a lighter model (`ollama pull llama3.2:3b`) and swap
`OLLAMA_MODEL` in `.env`, or set those pins to `groq` in
`gateway/agent_routing.yaml` (privacy note: groq is cloud).
For the assignment, the total wall time was ~12 minutes; all 5 parallel
nodes completed and the formatter produced a report.
