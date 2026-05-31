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
