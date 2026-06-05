# Demo Script — File Organiser Agent (EAGv3 Session 8)

Target: ≤ 5 minutes total screen time.
Format: screen-recorded terminal + browser split, no voiceover cuts needed.

---

## Setup (off-camera, before recording)

1. Gateway running: `cd gateway && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8108`
2. Dashboard running: `cd code && .venv\Scripts\python.exe run_ui.py` → http://localhost:8110
3. A completed scan session already loaded (run `run_organiser.py` beforehand so the
   History tab has at least one session visible from the start).
4. Ensure `demo_messy_drive/Downloads/IMG_20260601_165420.txt` is present (the
   deliberately-misclassified file for the critic-fail demo).

---

## Shot 1 — Messy drive and parallel fan-out [~60 s] (Req 1 + Req 2)

**Show:** file tree of `demo_messy_drive/` in a terminal or file explorer.

Point out:
- `Documents/` — four financial files (PAN, Form16, HDFC statement, salary slip)
- `Downloads/` — mixed receipts, a stray installer folder, old notes
- `Pictures/` — two photo stubs with duplicate copies in `backup/`
- `Projects/` — well-organised session folders (the "highlight" zone)
- `Downloads/SetupTool_v3_extracted/` — installer folder, 4 files inside

**Run in terminal:**

```
cd code
.venv\Scripts\python.exe run_organiser.py
```

**Show live output as nodes fire:**

```
[run_organiser] scanning … demo_messy_drive
[run_organiser] 18 files, 4 sensitive, 2 dup groups — handing to DAG

session s8-xxxx …
[n:1] planner          complete (5 s)
[n:2] pattern_analyzer complete (12 s)    ← these three lines print
[n:3] sensitive_detector …               ← almost simultaneously
[n:4] classifier …                       ← proving parallel fan-out
[n:6] classifier …
[n:8] classifier …
```

**Narration cue:** "Five nodes fire at once — the DAG is the product, not just
infrastructure. Classifying receipts doesn't depend on classifying photos."

---

## Shot 2 — NiceGUI dashboard: DAG, findings, privacy panel [~75 s] (Req 2 + Req 5)

**Open browser → http://localhost:8110 → Dashboard tab.**

Walk through the Dashboard in order:

1. **Stat cards** — "18 files · 4 sensitive · 2 duplicate groups · scan in 0.01 s."

2. **DAG SVG** — scroll to the graph. Point out:
   - The Planner node at left.
   - Three Classifier nodes + pattern_analyzer + sensitive_detector branching off in
     the same layer (visually parallel).
   - Critic nodes gating each classifier.
   - Formatter node at right waiting on all.
   - (If viewing a recovery session) recovery Planner node branching off a failed Critic.

3. **Classified findings** — expand a destination group (e.g. "Finance/Receipts/2026").
   - Show confidence bars next to each file.
   - Point out a file with a yellow "needs your eyes" badge.

4. **Private files panel** — show the four sensitive files listed with their metadata
   (name, size, suggested destination) and the label **"metadata only — content never
   read"**. Point at `HDFC_statement_Jan2026.txt` and `salary_slip_april2026.txt`.

**Narration cue:** "These four files were never opened. The sensitive-detector sees
only the filename and file size, and it runs on a local model — nothing leaves the
machine. This is the privacy contract."

5. **Already-organised panel** — show `Projects/EAGv3/` highlighted as a zone that
   scored well and was left untouched. Point out the Lock toggle.

---

## Shot 3 — Critic fail session in History [~60 s] (Req 3)

**Click the History tab.**

Select the session from `phase1_fail.log` (session ID **s8-465e6637**, 2026-06-04).

- Node count shows 45+ nodes; formatter-complete indicator is green.

**Click the session to expand it.** The DAG SVG loads.

Point out:
- Critic node (n:5) with a red ✗ icon.
- Recovery Planner node (n:11) branching off n:5 — the splice the orchestrator added
  at runtime.
- The chain: classifier → critic (fail) → recovery planner → new classifier → critic
  (pass) → formatter.

**For the IMG-misclassification story** (session s8-e0cc1855, log not captured in
`code/logs/` but present in `state/sessions/`): describe from HANDOFF evidence —
"In a separate run, critic n:30 saw `IMG_20260601_165420.txt` routed to Pictures/
but its extension is `.txt` and the preview is sprint-meeting notes. Verdict: fail.
Recovery planner n:33 was spliced in to re-classify it to Documents/."

**Narration cue:** "The critic is the quality gate. It failed the misclassified file,
the orchestrator spliced a recovery branch into the live graph, and the corrected
destination reached the formatter."

---

## Shot 4 — Coder + SandboxExecutor: population query [~45 s] (Req 4)

**In the History tab, select the London/Paris/Berlin session (s8-a7853431).**

Show the DAG SVG:
- Three Researcher nodes running in parallel (London, Paris, Berlin).
- A Coder node receiving all three researcher outputs.
- A SandboxExecutor node immediately following Coder (auto-wired as
  `internal_successor` in `agent_config.yaml`).
- Formatter at the end.

Expand the Coder node's output (or show the terminal log for this session):

```
[n:5] coder            complete (4.0 s)   {"code": "…sha256 …", "rationale": "…"}
[n:6] sandbox_executor complete (0.1 s)   Paris and Berlin, difference 1,574,000
```

**Narration cue:** "The Coder wrote stdlib Python to compare the numbers, the
SandboxExecutor ran it in a subprocess (30-second timeout, scrubbed env), and the
Formatter quoted the exact integer from stdout. No hallucinated math."

---

## Shot 5 — Approve Medium Plan: dry-run → execute → undo [~60 s] (Req 5)

**Return to the Dashboard tab, select a completed scan session.**

1. Click **"Approve Medium Plan"** (green button, top right of Dashboard).

2. **Dry-run dialog appears:**
   - List of planned moves (source → destination) from the classifier outputs.
   - Reclaimable bytes from duplicate pairs.
   - Any conflicts highlighted in red (if dst already exists with different content).

3. **Click Execute** — show the status label change to "Applying moves…" then
   "Done — N files moved."

4. **Undo button appears** (orange, bottom of dialog). Click it.
   - Status changes to "Undo complete. Files restored to original locations."

**Narration cue:** "Dry-run first — never a silent overwrite. The undo log is written
atomically before each rename, so a crash mid-batch leaves a recoverable record.
One click to reverse the whole batch."

---

## Shot 6 — Compare Plans and Filter Files [~45 s] (Req 6 / Req 7)

**Click the Compare Plans tab.**

- Three columns: Minimal / Medium (recommended badge) / Best.
- Cumulative diff row shows what each tier adds over the previous one.
- Point out: "Medium adds receipts grouping; Best adds aggressive archive of old
  downloads."

**Click the Filter Files tab.**

Demonstrate all three filter tiers:

1. **Structured** — set Category to "Finance" or drag the confidence slider to 90%.
   File list narrows instantly (client-side).

2. **Semantic** — click the destination combobox, choose "Finance/Receipts/2026".
   Shows only files with that pre-computed label.

3. **Natural-language box** — type `show me anything that needs review`.
   In-process keyword match highlights files with `needs_review: true` without
   an LLM round-trip.

**Narration cue:** "Three-tier filtering: instant structured filters, semantic labels
computed once during the scan, and a plain-language box for fuzzy intent — all
client-side, no extra LLM call."

---

## Wrap-up [~15 s]

Terminal: `cd code && .venv\Scripts\python.exe -m pytest tests/ -q`

Show: **28 passed** in ~N seconds. `flow.py` untouched (proven by
`test_no_orchestrator_modification_needed`).

**Narration cue:** "28 tests pass. The orchestrator was never modified. Everything
new is a prompt, a yaml entry, or a pure-Python helper."

---

*Total target: ≤ 5 minutes. Shots 1–6 + wrap-up = ~360 s.*
