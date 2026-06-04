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
  Tier 2 — semantic. NOT done here. The DAG's classifier / pattern_analyzer
           nodes do that, only on what survives tiers 0-1.

Output is a manifest dict the Planner and skills consume as USER_QUERY
context. Nothing here calls an LLM or reads sensitive content.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections import defaultdict
from pathlib import Path

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
    sensitive-content reads."""
    root = Path(root).resolve()
    t0 = time.time()

    files: list[dict] = []
    skipped_folders: list[dict] = []
    sensitive: list[dict] = []
    hashes: dict[str, list[str]] = defaultdict(list)

    # We walk top-down so we can prune installer/vcs/build dirs before
    # descending into them — the folder short-circuit.
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        # Folder short-circuit: prune recognised dirs in-place so os.walk
        # does not descend, and record why.
        pruned = []
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
                pruned.append(d)

        for fn in filenames:
            p = dp / fn
            try:
                st = p.stat()
            except OSError:
                continue
            rel = str(p.relative_to(root))
            ext = p.suffix.lower()
            desc = {
                "name": fn,
                "ext": ext,
                "size_bytes": st.st_size,
                "path": rel,
                "modified": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)),
            }
            # Tier-1 sensitive prefilter — metadata only.
            if SENSITIVE_SIGNALS.search(fn) or SENSITIVE_SIGNALS.search(rel):
                desc["sensitive_candidate"] = True
                sensitive.append(desc)
                # Sensitive files are still hashed (dedup is safe — hashing
                # is not "reading content" in any semantic sense) but never
                # classified or previewed.
            else:
                # Cheap content preview for the classifier / critic.
                # Only small, non-sensitive text files; never reads sensitive ones.
                if ext in _PREVIEW_EXTS and st.st_size <= _PREVIEW_MAX_BYTES:
                    try:
                        with open(p, "r", encoding="utf-8", errors="replace") as fh:
                            snippet = fh.read(_PREVIEW_CHARS).strip()
                        if snippet:
                            desc["preview"] = snippet
                    except OSError:
                        pass
            files.append(desc)
            try:
                hashes[_sha256(p)].append(rel)
            except OSError:
                pass

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

    return {
        "root": str(root),
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_seconds": round(time.time() - t0, 3),
        "tier0_file_count": len(files),
        "files": files,
        "sensitive_candidates": sensitive,
        "duplicate_groups": duplicates,
        "skipped_folders": skipped_folders,
        "folder_summary": list(folder_summary.values()),
    }


if __name__ == "__main__":
    import json
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(scan(root), indent=2, default=str))
