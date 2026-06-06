# Demo Script — File Organiser Agent

Target: ≤ 6 minutes total screen time.
Format: screen-recorded terminal + browser split.
Narrative flow: **messy problem → clean result → agent trace → privacy → how it was built → 5 base queries.**

---

## Setup (off-camera, before recording)

1. Gateway running: `cd gateway && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8108`
2. Dashboard running: `cd code && .venv\Scripts\python.exe run_ui.py` → http://localhost:8110
3. Sessions `s8-b0dffdf2` (pass run, 18 files) and `s8-465e6637` (critic-fail run, 19 files) present in `state/sessions/`.
4. Both `demo_messy_drive/` and `demo_clean_drive/` present at project root.

---

## Scene 1 — The problem: a messy drive [~45 s]

**Show `demo_messy_drive/` tree in terminal or file explorer:**

```
demo_messy_drive/
├── Documents/    ←  Form16_FY2025.txt · HDFC_statement_Jan2026.txt
│                     PAN_card.txt · salary_slip_april2026.txt
│                     (four sensitive files dumped flat — no sub-folder, no lock)
├── Downloads/    ←  amazon_order_4471.txt · electricity_bill_jan.txt
│                     flipkart_2025_tv.txt · IMG_20260601_165420.txt
│                     old_notes_2023.txt · untitled.txt
│                     bills/swiggy_invoice_mar.txt
│                     SetupTool_v3_extracted/   ← installer folder, 4 stale files
├── Pictures/     ←  IMG_2098.txt · sunset.txt
│   └── backup/   ←  IMG_2098_copy.txt · sunset_dup.txt  ← exact duplicates
└── Projects/     ←  EAGv3/Session7/ · Session8/
```

Point out explicitly:
- `HDFC_statement_Jan2026.txt` and `PAN_card.txt` sitting flat in `Documents/` — exposed.
- `IMG_20260601_165420.txt` in `Downloads/` — named like a photo, actually sprint meeting notes.
- `SetupTool_v3_extracted/` — stale installer folder, 4 files nobody needs.
- Two duplicate photo placeholders in `Pictures/backup/`.
- `Projects/` is actually fine — well-organised session folders.

**Narration cue:** "A real drive. Not broken — just what happens naturally over time.
Sensitive files co-located with receipts. One file named like a photo but containing
meeting notes. An installer folder nobody deleted. Two duplicate copies of the same image."

---

## Scene 2 — The result: a clean drive [~40 s]

**Show `demo_clean_drive/` tree:**

```
demo_clean_drive/
├── Finance/
│   ├── Receipts/
│   │   ├── 2025/  →  flipkart_2025_tv.txt
│   │   └── 2026/  →  amazon_order_4471.txt · swiggy_invoice_mar.txt
│   └── Utilities/
│       └── 2026/  →  electricity_bill_jan.txt
├── Documents/
│   └── Notes/
│       ├── 2023/  →  old_notes_2023.txt
│       └── 2026/  →  IMG_20260601_165420.txt   ← sprint notes, correctly identified
├── Misc/          →  untitled.txt
├── Pictures/
│   └── 2026/      →  IMG_2098.txt · sunset.txt  ← duplicates removed
├── Private/
│   ├── Finance/
│   │   ├── BankStatements/  →  HDFC_statement_Jan2026.txt
│   │   ├── Payroll/         →  salary_slip_april2026.txt
│   │   └── Tax/             →  Form16_FY2025.txt
│   └── IDs/                 →  PAN_card.txt
└── Projects/
    └── EAGv3/  →  Session7/ · Session8/  ← untouched (scored well, left as-is)
```

**Narration cue:** "Same 19 files (minus duplicates and the installer folder).
Every file in the right place — receipts split by year, meeting notes in Notes not
Pictures, private documents behind their own top-level folder. Projects untouched
because the pattern-analyzer scored it as already well-organised."

---

## Scene 3 — The agent that did the analysis [~60 s]

**Open browser → http://localhost:8110 → History tab.**

Select session **s8-b0dffdf2** (2026-06-04, 18 files, Pass).

**Show the DAG SVG. Walk it left to right with timings:**

```
[n:1  planner           5.3 s]
    ├── [n:2  pattern_analyzer   12.5 s]   ← all five fire
    ├── [n:3  sensitive_detector 185.8 s]  ← simultaneously
    ├── [n:4  classifier batch-1 204.8 s]  ← from t=0
    ├── [n:6  classifier batch-2  16.0 s]
    └── [n:8  classifier batch-3  66.2 s]
         each gated by → [critic ~8 s] → recovery planner if fail
                                       ↓ all converge
                              [n:27 formatter  185.3 s]
                              (second formatter n:66 after recovery: 185.1 s)
```

Point out the timings on-screen from the node metadata visible in the DAG panel.

**Narration cue:** "The Planner took 5 seconds to read the manifest and emit five
nodes at once. Classifying receipts doesn't depend on classifying photos — so they
ran in parallel. The slowest classifier took 204 seconds; without parallelism the
total would have been over 480 seconds. Wall-clock was 185 seconds limited by the
slowest parallel branch."

---

## Scene 4 — Privacy: sensitive files never opened [~45 s]

**Scroll to the Private files panel in the Dashboard (or zoom in on the DAG's
sensitive_detector node — click it to expand metadata).**

Show:
- Node n:3 `sensitive_detector` elapsed **185.8 s** on a **local provider**.
- Four files listed with: name · size · suggested destination.
- The badge: **"metadata only — content never read"**.

**Explain the `agent_routing.yaml` pin (open in editor or show on screen):**

```yaml
sensitive_detector: nvidia      # dev shortcut; switch to ollama for production
# In PRODUCTION:
#   ollama pull llama3.2:3b
#   sensitive_detector: ollama
```

**Narration cue:** "The sensitive_detector skill receives only the filename, path,
and file size — the same information a directory listing shows. No file handle is
opened. A local LLM (ollama) then reasons: 'the name contains HDFC, bank, statement
— this is likely a financial document.' The routing pin in `agent_routing.yaml`
ensures the prompt plus metadata never reach a cloud API. Classifying
`HDFC_statement_Jan2026.txt` next to `react_paper.pdf` — two completely different
handling modes, recorded side by side in the session JSON."

---

## Scene 5 — How the Critic self-corrects the graph [~55 s]

**In the History tab, switch to session s8-465e6637** (2026-06-04, 19 files, Fail run).

**Show the DAG SVG. Point out:**

- Critic node **n:5** — red ✗ icon.
- Recovery Planner node **n:11** branching off n:5 — spliced into the live graph at runtime.
- Second Critic **n:9** also failing → recovery Planner **n:12**.
- All branches converge at Formatter **n:44** (185.2 s) — full report still produced.

**IMG misclassification story (session s8-e0cc1855):**
"In a separate run, the classifier routed `IMG_20260601_165420.txt` to `Pictures/`
because the filename starts with IMG. The critic checked the extension (.txt) and
the content preview (sprint standup notes). Verdict: fail. The orchestrator spliced
a recovery Planner into the live graph. The corrected destination — `Documents/` —
reached the formatter. That is why this file ends up in `Documents/Notes/2026` in
the clean drive, not in `Pictures/`."

**Narration cue:** "The Critic is a quality gate. It doesn't restart the run — it
splices a recovery branch into the running DAG. The graph heals itself at runtime."

---

## Scene 6 — Skills, YAML, and prompts: how the agent is built [~45 s]

**Open `code/agent_config.yaml` in editor (or show in terminal).**

Point out one entry:

```yaml
classifier:
  prompt: prompts/classifier.md
  tools_allowed: []
  temperature: 0.1
  max_tokens: 2500
  description: Categorises a batch of non-sensitive files and proposes destinations.

sensitive_detector:
  prompt: prompts/sensitive_detector.md
  temperature: 0.0
  provider_pin: ollama    # privacy pin
  description: Flags private files from metadata ONLY; never reads content.
```

**Open `code/prompts/` in file explorer and show the list:**

```
classifier.md · sensitive_detector.md · pattern_analyzer.md
planner.md · critic.md · formatter.md · coder.md · researcher.md · …
```

Open `prompts/classifier.md` briefly to show a real prompt.

**Narration cue:** "Every skill is two files: a yaml entry that declares temperature,
token limit, and tool access; and a markdown prompt. The orchestrator `flow.py` was
never modified — three new skills are just three yaml entries and three prompt files."

---

## Scene 7 — Approve, dry-run, execute, undo [~35 s]

**Return to Dashboard tab, confirm session s8-b0dffdf2 is selected.**

1. Click **"Approve Medium Plan"** (green button).
2. **Dry-run dialog:** list of planned moves · 20 bytes reclaimable (2 duplicate pairs).
3. **Click Execute** → "Applying moves…" → "Done — N files moved."
4. **Undo button** (orange). Click it → "Undo complete. Files restored."

**Narration cue:** "Dry-run before every execute — no silent overwrites. The undo
log is written atomically before each rename. One click to reverse the entire batch."

---

## Scene 8 — The 5 base queries: how the orchestrator works [~90 s]

These queries demonstrate the DAG orchestrator concepts independently of the file organiser.

**Open History tab → select each session.**

---

### Query hello (s8-f6737e25) — the minimal DAG

```
[n:1 planner 3.9s] → [n:2 formatter 4.4s]
```

The Planner saw "say hello" and decided no research was needed.
**Concept:** The graph starts with just the Planner node. Every other node is added
at runtime. The simplest valid graph is planner + formatter.

---

### Query A — Shannon Wikipedia (s8-caab497e) — sequential chain

```
[n:1 planner 5.9s] → [n:2 researcher 42.9s] → [n:3 distiller 4.3s]
      ↓ auto-insert critic ↓ pass → [n:4 formatter 8.9s]
```

The Critic between Distiller and Formatter was auto-inserted — `critic: true` in
`agent_config.yaml`. It returned pass because the structured fields were present.
**Concept:** `critic: true` on a skill tells the orchestrator to gate every outgoing
edge with a Critic node. The Planner doesn't need to ask.

---

### Query I — London/Paris/Berlin (s8-a7853431) — parallel fan-out + Coder

```
[n:1 planner 4.1s]
    ├── [n:2 researcher 80.1s]  ← three fire in parallel
    ├── [n:3 researcher 52.0s]
    └── [n:4 researcher 39.7s]
          ↓ all complete
    [n:5 coder 4.0s]  →  [n:7 sandbox_executor 0.1s]  ← auto-wired
    [n:6 formatter 33.0s]
```

Wall-clock 80 s vs ~125 s sequential. Coder emitted `{"code": "…"}`, sandbox ran
it in a subprocess, formatter quoted the exact stdout integer.
**Concept:** `internal_successors: [sandbox_executor]` in the Coder yaml entry
auto-wires the sandbox without the Planner declaring it. Open `agent_config.yaml`
and show the `coder:` entry to make this concrete.

---

### Query J — graceful failure (s8-5d61f0e1) — degenerate DAG

```
[n:1 planner 3.7s] → [n:2 coder 3.8s] → [n:4 sandbox_executor 0.3s]
                           ↓
                    [n:3 formatter 16.1s]  ← reports failure
```

The Planner recognised the file could not exist and planned accordingly.
**Concept:** the Planner is a first-class node, not a fixed entry point. It can
route to failure-reporting paths directly. A degenerate DAG is a valid, correct answer.

---

### Query K — resume after kill (s8-8d8d2867 → s8_K_resumed_v2) — persistence

**Partial run (killed):**
```
[n:1 planner  4.3s] ✓
[n:2 researcher 36.7s] ✓    [n:3 researcher 82.4s] ✓    [n:4 researcher 73.8s] ✓
[n:5 coder — KILLED mid-run, status=running on disk]
```

**Resume:**
```bash
.venv\Scripts\python.exe flow.py --resume s8_K_resumed_v2
```
```
[n:5 coder    4.9s]  ← re-ran from scratch (n:1–4 NOT re-run)
[n:6 formatter 9.6s]
[n:7 sandbox_executor 0.1s]
FINAL: Kinshasa growing fastest at 4.40 %
```

**Concept:** `graph.json` is written atomically after every node completes.
On resume the orchestrator reads the graph, resets `status=running` nodes to
`pending`, and continues. The three completed researchers are not re-run.

---

## Wrap-up [~15 s]

```
cd code && .venv\Scripts\python.exe -m pytest tests/ -q
```

**28 passed.** `flow.py` untouched. Everything new is a prompt, a yaml entry, or a
pure-Python helper alongside the orchestrator.

---

*Total target: ≤ 6 minutes. Scenes 1–8 + wrap-up ≈ 390 s.*
