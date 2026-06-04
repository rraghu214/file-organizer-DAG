"""DAG SVG builder — pure string generation, no NiceGUI dependency."""
from __future__ import annotations

from collections import defaultdict

SKILL_COLOR: dict[str, str] = {
    "planner":            "#6366f1",
    "classifier":         "#0ea5e9",
    "critic":             "#f59e0b",
    "sensitive_detector": "#ef4444",
    "pattern_analyzer":   "#8b5cf6",
    "formatter":          "#10b981",
    "coder":              "#f97316",
    "sandbox_executor":   "#6b7280",
    "researcher":         "#3b82f6",
    "distiller":          "#06b6d4",
}

STATUS_ICON: dict[str, str] = {
    "complete": "✓",
    "failed":   "✗",
    "skipped":  "⊘",
    "running":  "⟳",
    "pending":  "○",
}

# Node box dimensions and gaps
_NW, _NH   = 130, 44
_HGAP, _VGAP = 22, 34
_PAD = 22


def _longest_path_layers(node_ids: list[str], edges: list[dict]) -> dict[str, int]:
    id_set = set(node_ids)
    pred: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in id_set and t in id_set:
            pred[t].append(s)

    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        parents = pred.get(nid, [])
        memo[nid] = (max(depth(p) for p in parents) + 1) if parents else 0
        return memo[nid]

    for nid in node_ids:
        depth(nid)
    return memo


def build(session: dict) -> str:
    """Return an SVG string for the session's DAG."""
    g = session.get("graph", {})
    node_states = session.get("nodes", {})
    raw_nodes = g.get("nodes", [])
    edges = g.get("edges", [])

    if not raw_nodes:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="380" height="54">'
            f'<text x="10" y="33" font-size="13" fill="#9ca3af">No graph data yet.</text>'
            f"</svg>"
        )

    all_ids = [n["id"] for n in raw_nodes]
    layers = _longest_path_layers(all_ids, edges)

    layer_groups: dict[int, list[dict]] = defaultdict(list)
    for n in raw_nodes:
        layer_groups[layers.get(n["id"], 0)].append(n)
    for lst in layer_groups.values():
        lst.sort(key=lambda x: x.get("metadata", {}).get("label") or x["id"])

    # Centre positions
    pos: dict[str, tuple[int, int]] = {}
    max_layer = max(layer_groups) if layer_groups else 0
    for li in range(max_layer + 1):
        for col, n in enumerate(layer_groups.get(li, [])):
            cx = _PAD + col * (_NW + _HGAP) + _NW // 2
            cy = _PAD + li * (_NH + _VGAP) + _NH // 2
            pos[n["id"]] = (cx, cy)

    svg_w = _PAD * 2 + max(
        len(layer_groups.get(li, [])) * (_NW + _HGAP) - _HGAP
        for li in layer_groups
    )
    svg_h = _PAD * 2 + (max_layer + 1) * (_NH + _VGAP) - _VGAP

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}"'
        f' style="font-family:ui-sans-serif,system-ui,sans-serif;">',
        "<defs>"
        '<marker id="arr" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">'
        '<path d="M0,0 L0,7 L7,3.5 z" fill="#cbd5e1"/>'
        "</marker>"
        "</defs>",
    ]

    # Edges
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in pos and t in pos:
            x1, y1 = pos[s]
            x2, y2 = pos[t]
            parts.append(
                f'<line x1="{x1}" y1="{y1 + _NH // 2}" '
                f'x2="{x2}" y2="{y2 - _NH // 2}" '
                f'stroke="#cbd5e1" stroke-width="1.5" marker-end="url(#arr)"/>'
            )

    # Nodes
    for n in raw_nodes:
        if n["id"] not in pos:
            continue
        cx, cy = pos[n["id"]]
        x, y = cx - _NW // 2, cy - _NH // 2
        skill = n.get("skill", "?")
        label = n.get("metadata", {}).get("label") or n["id"].replace("n:", "")

        ns = node_states.get(n["id"])
        status = (ns["status"] if ns else None) or n.get("status", "pending")

        fill    = SKILL_COLOR.get(skill, "#6b7280")
        opacity = "1.0" if status == "complete" else "0.42" if status in ("failed", "skipped") else "0.72"
        stroke  = "#dc2626" if status == "failed" else "rgba(255,255,255,0.25)"
        icon    = STATUS_ICON.get(status, "")

        parts += [
            f'<rect x="{x}" y="{y}" width="{_NW}" height="{_NH}" rx="7" '
            f'fill="{fill}" fill-opacity="{opacity}" '
            f'stroke="{stroke}" stroke-width="1.2"/>',
            # skill name (bold, top half)
            f'<text x="{cx}" y="{cy - 5}" text-anchor="middle" '
            f'fill="white" font-size="10" font-weight="700">{skill}</text>',
            # label + status icon (dim, bottom half)
            f'<text x="{cx}" y="{cy + 11}" text-anchor="middle" '
            f'fill="rgba(255,255,255,0.82)" font-size="9">{label} {icon}</text>',
        ]

    parts.append("</svg>")
    return "\n".join(parts)
