"""Data layer: reads state/sessions/<sid>/ JSON; no agent logic."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

SESSIONS_DIR = Path(__file__).parent.parent / "state" / "sessions"


# ── Session listing ───────────────────────────────────────────────────────────

def list_sessions() -> list[str]:
    """Session IDs sorted most-recent first (hex timestamp in name)."""
    folders = [
        d.name for d in SESSIONS_DIR.iterdir()
        if d.is_dir() and d.name != ".gitkeep"
    ]

    def _key(name: str):
        m = re.match(r"s8-([0-9a-f]+)$", name)
        return (0, int(m.group(1), 16)) if m else (1, name)

    return sorted(folders, key=_key, reverse=True)


# ── Full session load ─────────────────────────────────────────────────────────

def load_session(sid: str) -> dict:
    """Return {sid, query, graph, nodes} from disk."""
    base = SESSIONS_DIR / sid

    query = ""
    if (base / "query.txt").exists():
        query = (base / "query.txt").read_text(encoding="utf-8")

    graph: dict = {}
    if (base / "graph.json").exists():
        try:
            graph = json.loads((base / "graph.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    nodes: dict[str, dict] = {}
    nodes_dir = base / "nodes"
    if nodes_dir.exists():
        for f in sorted(nodes_dir.glob("n_*.json")):
            if f.suffix == ".json" and not f.name.endswith(".tmp"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    nid = data.get("node_id")
                    if nid:
                        nodes[nid] = data
                except (json.JSONDecodeError, KeyError):
                    pass

    return {"sid": sid, "query": query, "graph": graph, "nodes": nodes}


# ── Extractors ────────────────────────────────────────────────────────────────

def extract_scan(query: str) -> dict:
    """Pull SCAN_RESULT JSON block from the query string."""
    m = re.search(r"SCAN_RESULT:\s*(\{.*)", query, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def classified_items(session: dict) -> list[dict]:
    """Merge all complete classifier outputs; deduplicate by (name, destination)."""
    items: list[dict] = []
    for n in session["nodes"].values():
        if n["skill"] != "classifier" or n["status"] != "complete":
            continue
        out = (n.get("result") or {}).get("output", {})
        # output may arrive as a raw list or as {"classified": [...]}
        batch = out if isinstance(out, list) else out.get("classified", [])
        items.extend(batch)

    seen: set = set()
    unique: list[dict] = []
    for item in items:
        key = (item.get("name"), item.get("destination"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def sensitive_files(session: dict) -> list[dict]:
    """Return flagged list from the first complete sensitive_detector node."""
    for n in session["nodes"].values():
        if n["skill"] == "sensitive_detector" and n["status"] == "complete":
            out = (n.get("result") or {}).get("output", {})
            return out.get("flagged", [])
    return []


def pattern_analysis(session: dict) -> dict | None:
    """Most recent complete pattern_analyzer output (highlights + plans)."""
    candidates = [
        n for n in session["nodes"].values()
        if n["skill"] == "pattern_analyzer"
        and n["status"] == "complete"
        and (n.get("result") or {}).get("output")
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x.get("completed_at") or 0)
    return (best.get("result") or {}).get("output")


def formatter_output(session: dict) -> str | None:
    """The final_answer string from the formatter node, if present."""
    for n in session["nodes"].values():
        if n["skill"] == "formatter" and n["status"] == "complete":
            out = (n.get("result") or {}).get("output", {})
            return out.get("final_answer")
    return None


def group_by_destination(items: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        g[item.get("destination", "Uncategorised")].append(item)
    return dict(g)


def session_stats(session: dict) -> dict:
    """Quick summary counts for the header cards."""
    scan = extract_scan(session["query"])
    nodes = session["nodes"].values()
    return {
        "file_count":    scan.get("tier0_file_count", "—"),
        "sensitive":     len(sensitive_files(session)),
        "dup_groups":    len(scan.get("duplicate_groups", [])),
        "skipped":       len(scan.get("skipped_folders", [])),
        "node_count":    len(list(nodes)),
        "complete":      sum(1 for n in nodes if n["status"] == "complete"),
        "failed":        sum(1 for n in nodes if n["status"] == "failed"),
    }
