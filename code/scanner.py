"""Tier-0 / Tier-1 file scanner — the cheap index that feeds the DAG.

This is the part inspired by Everything's methodology: do the cheapest
work first so the expensive LLM tier (the classifier / pattern_analyzer
nodes) only ever sees what genuinely needs judgment.

Three tiers, cheapest first:

  Tier 0 — structural. os.scandir walk: name, ext, size, mtime, path.
           (On Windows the production tool would read the MFT / query the
           Everything SDK instead; scandir is the portable fallback.)
  Tier 1 — cheap signals, no LLM:
             * SHA-256 hashing -> exact-duplicate groups
             * folder short-circuit: installer-extract / vcs / build dirs
               are recognised at the folder boundary and NOT descended
             * sensitive prefilter: filename/path regex marks likely
               private files so the planner routes them to the
               sensitive_detector (local) and never to a cloud classifier
             * mtime/size change-detection (speed layer): files unchanged
               since the last scan are skipped before hashing
             * processed-ledger check (correctness layer): files whose
               content-hash was already moved in a previous session are
               emitted as already_handled, not in the main files[] array
  Tier 2 — semantic. NOT done here. The DAG's classifier / pattern_analyzer
           nodes do that, only on what survives tiers 0-1.

Output is a manifest dict the Planner and skills consume as USER_QUERY
context. Nothing here calls an LLM or reads sensitive content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

# ── scan_config.yaml ─────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "scan_config.yaml"
_STATE_DIR   = Path(__file__).parent / "state"
_LEDGER_PATH = _STATE_DIR / "ledger.json"
_SCAN_STATE_PATH = _STATE_DIR / "scan_state.json"


def _parse_yaml_config(path: Path) -> dict:
    """Minimal inline YAML parser for our fixed config format.

    Handles: `key: []`, `key: true/false`, indented list items `  - value`.
    No external dependency; only covers keys we actually use.
    """
    result: dict = {}
    current_list_key: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].rstrip()          # strip comments
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            if current_list_key is not None:
                result[current_list_key].append(stripped[2:].strip().strip("\"'"))
        elif ":" in line:
            current_list_key = None
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "[]":
                result[key] = []
            elif val == "":
                result[key] = []
                current_list_key = key
            elif val.lower() == "true":
                result[key] = True
            elif val.lower() == "false":
                result[key] = False
            else:
                result[key] = val.strip("\"'")
    return result


def _load_scan_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return _parse_yaml_config(_CONFIG_PATH)
        except Exception:
            pass
    return {}


def _save_scan_config(config: dict) -> None:
    """Write back scan_config.yaml, preserving the header comment block."""
    lines = [
        "# scan_config.yaml — FileOrganiser scan settings.",
        "# Read by scanner.py at the start of every scan.",
        "# Edit manually or via the Lock toggles in the UI (locked_zones is auto-updated).",
        "",
        "# Restrict the scan to only these paths (relative to the scan root).",
        "# An empty list means scan the entire root.",
        "include_paths:",
    ]
    for p in config.get("include_paths", []):
        lines.append(f"  - {p}")
    if not config.get("include_paths"):
        lines[-1] = "include_paths: []"

    lines += [
        "",
        "# Never walk these paths (relative to the scan root, prefix-matched).",
        "exclude_paths:",
    ]
    for p in config.get("exclude_paths", []):
        lines.append(f"  - {p}")
    if not config.get("exclude_paths"):
        lines[-1] = "exclude_paths: []"

    lines += [
        "",
        "# Zones the user has locked in the UI — never suggested for reorganisation.",
        "locked_zones:",
    ]
    for p in config.get("locked_zones", []):
        lines.append(f"  - {p}")
    if not config.get("locked_zones"):
        lines[-1] = "locked_zones: []"

    use_ei = "true" if config.get("use_everything_index") else "false"
    lines += [
        "",
        "# Set to true to use the voidtools Everything SDK for Tier-0 (Windows only).",
        f"use_everything_index: {use_ei}",
    ]

    _atomic_write_text(_CONFIG_PATH, "\n".join(lines) + "\n")


def _atomic_write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    os.replace(tmp, path)


# ── scan_state + ledger I/O ────────────────────────────────────────────────────

def _load_scan_state() -> dict:
    """Load {abs_path: {mtime, size}} from state/scan_state.json."""
    if _SCAN_STATE_PATH.exists():
        try:
            return json.loads(_SCAN_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_ledger() -> dict:
    """Load {sha256_hex: {destination, sid, ...}} from state/ledger.json."""
    if _LEDGER_PATH.exists():
        try:
            return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def update_ledger(entries: list[dict]) -> None:
    """Add completed-move records to the processed ledger.

    Called by the executor after apply() to register moved files so
    re-scans can skip them.  Each entry: {hash, destination, name, sid}.
    """
    ledger = _load_ledger()
    for e in entries:
        h = e.get("hash", "")
        if h:
            ledger[h] = {
                "destination": e.get("destination", ""),
                "name":        e.get("name", ""),
                "sid":         e.get("sid", ""),
                "timestamp":   e.get("timestamp", ""),
            }
    _atomic_write_json(_LEDGER_PATH, ledger)

# Folder names that are recognised and skipped at the folder boundary —
# no per-file work happens inside them.
SHORT_CIRCUIT_DIRS = re.compile(
    r"(_extracted$|node_modules$|\.git$|__pycache__$|\.venv$|venv$|"
    r"build$|dist$|\.idea$|setup.*extract)", re.I)

# Filename / path signals that mark a file as likely sensitive. These files
# are flagged from METADATA ONLY and never have their content read here.
SENSITIVE_SIGNALS = re.compile(
    r"(salary|payslip|pay[_-]?slip|statement|bank|aadhaar|aadhar|"
    r"(?:^|[_\-\s])pan(?:[_\-\s]|card|$)|passport|form[_-]?16|itr|tax|ssn|"
    r"credential|password|\.kdbx$|\.pem$|\.key$)", re.I)

INSTALLER_MARKERS = (".exe", ".dll", ".msi", ".manifest")

# Extensions and size threshold for cheap content-preview extraction.
# Preview gives the classifier a stronger signal than filename alone and
# lets the Critic cross-check destination vs actual content.
# Sensitive files are NEVER previewed regardless of extension.
_PREVIEW_EXTS = {".txt", ".md", ".py", ".js", ".html", ".css"}
_PREVIEW_MAX_BYTES = 600  # skip large files; preview only stubs / small docs
_PREVIEW_CHARS = 300


def _sha256(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _looks_like_installer(dirpath: Path) -> bool:
    # Name signal is the primary, reliable check.
    if SHORT_CIRCUIT_DIRS.search(dirpath.name):
        return True
    # Secondary heuristic: this folder's OWN direct files (not the whole
    # subtree) are dominated by installer binaries AND it carries an
    # install manifest. Recursing into the subtree here was a bug — a
    # parent like Downloads/ that merely contains one installer folder
    # would be misjudged as an installer itself.
    try:
        direct = [p for p in dirpath.iterdir() if p.is_file()]
    except OSError:
        return False
    if not direct:
        return False
    exts = [p.suffix.lower() for p in direct]
    has_manifest = any(p.name.endswith(".manifest") for p in direct)
    binary_ratio = sum(e in INSTALLER_MARKERS for e in exts) / len(exts)
    return has_manifest and binary_ratio > 0.5


def scan(root: str | Path) -> dict:
    """Walk `root` and return the tiered manifest. Cheap; no LLM, no
    sensitive-content reads.

    Phase 3 additions (all backward-compatible — fresh runs behave identically):
    - Respects scan_config.yaml: exclude_paths / locked_zones prune the walk;
      include_paths restrict to sub-trees; Triage Planner gets an
      exclusion_note so it does not plan work on excluded zones.
    - mtime/size change-detection (state/scan_state.json): files unchanged
      since the last scan skip SHA-256 re-hashing (speed layer); cached hash
      is still used so duplicate detection works across re-scans.
    - Processed-ledger check (state/ledger.json): files already moved in a
      prior session are emitted as already_handled, not in files[] (correctness
      layer — prevents re-classifying completed work).
    """
    root = Path(root).resolve()
    t0   = time.time()

    # ── load phase-3 state ────────────────────────────────────────────────
    config     = _load_scan_config()
    scan_state = _load_scan_state()
    ledger     = _load_ledger()

    exclude_rel: list[str] = list(config.get("exclude_paths", []))
    locked_rel:  list[str] = list(config.get("locked_zones",  []))
    all_excluded = {p.replace("/", os.sep) for p in exclude_rel + locked_rel}
    include_rel:  list[str] = list(config.get("include_paths", []))
    active_exclusions: list[str] = sorted(all_excluded)

    files: list[dict]            = []
    already_handled: list[dict]  = []
    skipped_folders: list[dict]  = []
    sensitive: list[dict]        = []
    hashes: dict[str, list[str]] = defaultdict(list)
    new_scan_state: dict         = dict(scan_state)   # carry forward all entries

    # We walk top-down so we can prune installer/vcs/build dirs before
    # descending into them — the folder short-circuit.
    for dirpath, dirnames, filenames in os.walk(root):
        dp      = Path(dirpath)
        rel_dir = str(dp.relative_to(root))

        # include_paths: only descend into matching sub-trees (skip if set)
        if include_rel and rel_dir != ".":
            if not any(
                rel_dir == inc or rel_dir.startswith(inc + os.sep)
                for inc in include_rel
            ):
                dirnames.clear()
                continue

        # exclude / locked paths: prune walk and skip this directory
        if all_excluded and rel_dir != ".":
            if any(
                rel_dir == exc or rel_dir.startswith(exc + os.sep)
                for exc in all_excluded
            ):
                dirnames.clear()
                continue

        # Folder short-circuit: prune recognised dirs in-place so os.walk
        # does not descend, and record why.
        for d in list(dirnames):
            child = dp / d
            if _looks_like_installer(child):
                skipped_folders.append({
                    "path": str(child.relative_to(root)),
                    "reason": "installer-extract / build dir — recognised at "
                              "folder level, not descended",
                    "file_count": sum(1 for _ in child.rglob("*") if _.is_file()),
                })
                dirnames.remove(d)

        for fn in filenames:
            p = dp / fn
            try:
                st = p.stat()
            except OSError:
                continue
            abs_str = str(p)
            rel     = str(p.relative_to(root))
            ext     = p.suffix.lower()
            mtime   = st.st_mtime
            size    = st.st_size
            desc = {
                "name":       fn,
                "ext":        ext,
                "size_bytes": size,
                "path":       rel,
                "modified":   time.strftime("%Y-%m-%d", time.localtime(mtime)),
            }

            # ── Tier-1a: mtime/size change-detection (speed layer) ────────
            cached = scan_state.get(abs_str)
            if cached and cached.get("mtime") == mtime and cached.get("size") == size:
                # File unchanged — reuse cached hash so dedup still works
                cached_hash = cached.get("hash", "")
                if cached_hash:
                    hashes[cached_hash].append(rel)
                    if cached_hash in ledger:
                        desc["already_handled"] = True
                        desc["ledger_entry"]    = ledger[cached_hash]
                        already_handled.append(desc)
                        continue
                if cached.get("sensitive"):
                    desc["sensitive_candidate"] = True
                    sensitive.append(desc)
                files.append(desc)
                continue

            # ── Tier-1b: sensitive prefilter — metadata only ───────────────
            is_sensitive = bool(
                SENSITIVE_SIGNALS.search(fn) or SENSITIVE_SIGNALS.search(rel)
            )
            if is_sensitive:
                desc["sensitive_candidate"] = True
                sensitive.append(desc)
                # Sensitive files are still hashed (dedup is safe — hashing
                # is not "reading content" in any semantic sense) but never
                # classified or previewed.
            else:
                # Cheap content preview for the classifier / critic.
                # Only small, non-sensitive text files; never reads sensitive ones.
                if ext in _PREVIEW_EXTS and size <= _PREVIEW_MAX_BYTES:
                    try:
                        with open(p, "r", encoding="utf-8", errors="replace") as fh:
                            snippet = fh.read(_PREVIEW_CHARS).strip()
                        if snippet:
                            desc["preview"] = snippet
                    except OSError:
                        pass

            # ── Tier-1c: SHA-256 for dedup + ledger check ─────────────────
            fhash: str = ""
            try:
                fhash = _sha256(p)
                hashes[fhash].append(rel)
            except OSError:
                pass

            # Persist mtime + size + hash for next run's speed layer
            new_scan_state[abs_str] = {
                "mtime":     mtime,
                "size":      size,
                "hash":      fhash,
                "sensitive": is_sensitive,
            }

            # ── Tier-1d: processed-ledger check (correctness layer) ───────
            if fhash and fhash in ledger:
                desc["already_handled"] = True
                desc["ledger_entry"]    = ledger[fhash]
                already_handled.append(desc)
                continue  # do NOT add to main files[]

            files.append(desc)

    # Persist updated scan_state for the next run's speed layer
    _atomic_write_json(_SCAN_STATE_PATH, new_scan_state)

    # Tier-1 duplicate groups.
    duplicates = [
        {"hash": h[:12], "paths": paths, "count": len(paths)}
        for h, paths in hashes.items() if len(paths) > 1
    ]

    # Folder summary for the pattern_analyzer (cheap structural scoring hint).
    folder_summary: dict[str, dict] = {}
    for f in files:
        top = f["path"].split(os.sep)[0]
        s = folder_summary.setdefault(top, {"path": top, "file_count": 0,
                                            "exts": set()})
        s["file_count"] += 1
        s["exts"].add(f["ext"])
    for s in folder_summary.values():
        s["distinct_ext_count"] = len(s["exts"])
        s["exts"] = sorted(s["exts"])

    # Exclusion note for the Triage Planner prompt
    exclusion_note = ""
    if active_exclusions:
        shown = ", ".join(active_exclusions[:5])
        tail  = " …" if len(active_exclusions) > 5 else ""
        exclusion_note = (
            f"NOTE: {len(active_exclusions)} path(s) excluded from scan "
            f"(scan_config.yaml): {shown}{tail} — do NOT plan work on these zones."
        )

    return {
        "root":                str(root),
        "scanned_at":          time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_seconds":        round(time.time() - t0, 3),
        "tier0_file_count":    len(files),
        "files":               files,
        "sensitive_candidates": sensitive,
        "duplicate_groups":    duplicates,
        "skipped_folders":     skipped_folders,
        "folder_summary":      list(folder_summary.values()),
        "already_handled":     already_handled,
        "active_exclusions":   active_exclusions,
        "exclusion_note":      exclusion_note,
    }


if __name__ == "__main__":
    import json
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(scan(root), indent=2, default=str))
