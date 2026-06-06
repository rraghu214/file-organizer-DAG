"""DAG SVG builder — pure string generation, no NiceGUI dependency."""
from __future__ import annotations

import re
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
_NW, _NH   = 142, 58
_HGAP, _VGAP = 22, 28
_PAD = 22

# Virtual sentinel node id used only in SVG layout
_UQ_ID = "__USER_QUERY__"


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


def build(session: dict) -> tuple[str, list[str]]:
    """Return (svg_string, ordered_node_ids) for the session's DAG.

    The node_ids list is ordered top-to-bottom, left-to-right so the
    caller can build a matching click-detail list without re-parsing SVG.
    The virtual USER_QUERY entry node is NOT included in node_ids.
    """
    g = session.get("graph", {})
    node_states = session.get("nodes", {})
    raw_nodes = g.get("nodes", [])
    edges = g.get("edges", [])

    if not raw_nodes:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="380" height="54">'
            f'<text x="10" y="33" font-size="13" fill="#9ca3af">No graph data yet.</text>'
            f"</svg>",
            [],
        )

    all_ids = [n["id"] for n in raw_nodes]
    layers = _longest_path_layers(all_ids, edges)

    # If any real node takes USER_QUERY as input, inject a virtual entry node:
    # shift all layers by 1 and reserve layer 0 for the USER_QUERY pill.
    uq_targets = [n["id"] for n in raw_nodes if "USER_QUERY" in n.get("inputs", [])]
    has_uq = bool(uq_targets)
    if has_uq:
        layers = {k: v + 1 for k, v in layers.items()}

    layer_groups: dict[int, list[dict]] = defaultdict(list)
    for n in raw_nodes:
        layer_groups[layers.get(n["id"], 0 if not has_uq else 1)].append(n)
    for lst in layer_groups.values():
        lst.sort(key=lambda x: x.get("metadata", {}).get("label") or x["id"])

    # Centre positions for real nodes
    pos: dict[str, tuple[int, int]] = {}
    max_layer = max(layer_groups) if layer_groups else 0
    for li in range(max_layer + 1):
        for col, n in enumerate(layer_groups.get(li, [])):
            cx = _PAD + col * (_NW + _HGAP) + _NW // 2
            cy = _PAD + li * (_NH + _VGAP) + _NH // 2
            pos[n["id"]] = (cx, cy)

    # Width: widest layer (including layer 0 if it holds USER_QUERY pill)
    layer_widths: list[int] = [
        len(layer_groups.get(li, [])) * (_NW + _HGAP) - _HGAP
        for li in range(max_layer + 1)
        if layer_groups.get(li)
    ]
    _UQ_W = 120  # USER_QUERY pill width
    if has_uq:
        layer_widths.append(_UQ_W)

    svg_w = _PAD * 2 + max(layer_widths) if layer_widths else _PAD * 2 + _NW
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

    # USER_QUERY pill — clickable, single label, detail shown on click
    _UQ_H = 30
    uq_cx = uq_cy = 0
    if has_uq:
        uq_xs = [pos[nid][0] for nid in uq_targets if nid in pos]
        uq_cx = int(sum(uq_xs) / len(uq_xs)) if uq_xs else svg_w // 2
        uq_cy = _PAD + _NH // 2  # layer 0 vertical centre

        # Dashed edges from pill to target nodes
        for nid in uq_targets:
            if nid in pos:
                x2, y2 = pos[nid]
                parts.append(
                    f'<line x1="{uq_cx}" y1="{uq_cy + _UQ_H // 2}" '
                    f'x2="{x2}" y2="{y2 - _NH // 2}" '
                    f'stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,3" '
                    f'marker-end="url(#arr)"/>'
                )

        # Pill wrapped in <g data-uq> so the js_handler can detect clicks on it
        parts += [
            f'<g data-uq="1" style="cursor:pointer;">',
            f'<rect x="{uq_cx - _UQ_W // 2}" y="{uq_cy - _UQ_H // 2}" '
            f'width="{_UQ_W}" height="{_UQ_H}" rx="{_UQ_H // 2}" '
            f'fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.2"/>',
            f'<text x="{uq_cx}" y="{uq_cy + 4}" text-anchor="middle" '
            f'fill="#475569" font-size="10" font-weight="600">USER QUERY</text>',
            f'</g>',
        ]

    # Real node edges — each wrapped in a <g> for click support.
    # A wider transparent overlay line makes edges easy to click.
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in pos and t in pos:
            x1, y1 = pos[s]
            x2, y2 = pos[t]
            y1e, y2e = y1 + _NH // 2, y2 - _NH // 2
            src_esc = s.replace(":", "_").replace(".", "_")
            tgt_esc = t.replace(":", "_").replace(".", "_")
            parts += [
                f'<g data-esrc="{s}" data-etgt="{t}" '
                f'id="dag-edge-{src_esc}-{tgt_esc}" style="cursor:pointer;">',
                # Visible line
                f'<line class="dag-edge-vis" '
                f'x1="{x1}" y1="{y1e}" x2="{x2}" y2="{y2e}" '
                f'stroke="#cbd5e1" stroke-width="1.5" marker-end="url(#arr)"/>',
                # Wide invisible overlay — the actual click target
                f'<line x1="{x1}" y1="{y1e}" x2="{x2}" y2="{y2e}" '
                f'stroke="transparent" stroke-width="14"/>',
                '</g>',
            ]

    # Identify formatter nodes that produced the final answer (gold border).
    answer_nids: set[str] = {
        nid for nid, nd in node_states.items()
        if nd.get("skill") == "formatter"
        and nd.get("status") == "complete"
        and (nd.get("result") or {}).get("output", {}).get("final_answer")
    }

    # Real nodes — wrapped in <g> for click support
    ordered_ids: list[str] = []
    for li in range(max_layer + 1):
        for n in layer_groups.get(li, []):
            ordered_ids.append(n["id"])

    for n in raw_nodes:
        if n["id"] not in pos:
            continue
        cx, cy = pos[n["id"]]
        x, y = cx - _NW // 2, cy - _NH // 2
        skill = n.get("skill", "?")

        ns = node_states.get(n["id"])
        status = (ns["status"] if ns else None) or n.get("status", "pending")

        # Pull runtime metadata from the persisted AgentResult
        result     = (ns.get("result") or {}) if ns else {}
        elapsed_s  = result.get("elapsed_s")
        provider   = (result.get("provider") or "").strip()
        retries    = (ns.get("retries") or 0) if ns else 0

        # Info line: "5.3s · groq"  or just "5.3s" / "groq" / ""
        info_parts: list[str] = []
        if elapsed_s is not None and elapsed_s > 0:
            info_parts.append(f"{elapsed_s:.1f}s")
        if provider:
            info_parts.append(provider)
        info_line = " · ".join(info_parts)

        # Status icon — critics show verdict text for clarity
        base_icon = STATUS_ICON.get(status, "")
        if skill == "critic" and status == "complete":
            verdict = (result.get("output") or {}).get("verdict", "")
            if verdict == "pass":
                base_icon = "✓ pass"
            elif verdict == "fail":
                base_icon = "✗ fail"
        retry_tag = f" ↻{retries}" if retries > 0 else ""
        icon_line = base_icon + retry_tag

        fill    = SKILL_COLOR.get(skill, "#6b7280")
        opacity = "1.0" if status == "complete" else "0.42" if status in ("failed", "skipped") else "0.72"
        is_answer = n["id"] in answer_nids
        if is_answer:
            stroke, stroke_w = "#fbbf24", "2.5"
        elif status == "failed":
            stroke, stroke_w = "#dc2626", "1.5"
        else:
            stroke, stroke_w = "rgba(255,255,255,0.25)", "1.2"

        nid_safe = n["id"].replace(":", "_").replace(".", "_")
        parts += [
            f'<g data-nid="{n["id"]}" style="cursor:pointer;" id="dag-node-{nid_safe}">',
        ]
        if is_answer:
            parts.append(
                f'<rect x="{x - 3}" y="{y - 3}" width="{_NW + 6}" height="{_NH + 6}" rx="9" '
                f'fill="none" stroke="#fbbf24" stroke-width="1" opacity="0.5"/>'
            )
        parts += [
            f'<rect x="{x}" y="{y}" width="{_NW}" height="{_NH}" rx="7" '
            f'fill="{fill}" fill-opacity="{opacity}" '
            f'stroke="{stroke}" stroke-width="{stroke_w}"/>',
            # Row 1 — node id (small, dim)
            f'<text x="{cx}" y="{cy - 19}" text-anchor="middle" '
            f'fill="rgba(255,255,255,0.55)" font-size="8">{n["id"]}</text>',
            # Row 2 — skill name (bold, prominent)
            f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" '
            f'fill="white" font-size="10" font-weight="700">{skill}</text>',
            # Row 3 — elapsed time · provider
            f'<text x="{cx}" y="{cy + 8}" text-anchor="middle" '
            f'fill="rgba(255,255,255,0.80)" font-size="8.5">{info_line}</text>',
            # Row 4 — status icon / verdict + retries
            f'<text x="{cx}" y="{cy + 21}" text-anchor="middle" '
            f'fill="rgba(255,255,255,0.65)" font-size="8.5">{icon_line}</text>',
            '</g>',
        ]

    # ANSWER terminal oval — symmetric with USER QUERY at the top.
    # Appears below the last layer and connects from answer formatter(s).
    _ANS_W, _ANS_H = 100, 30
    if answer_nids:
        ans_xs = [pos[nid][0] for nid in answer_nids if nid in pos]
        ans_cx = int(sum(ans_xs) / len(ans_xs)) if ans_xs else svg_w // 2
        # Position one gap below the last real node layer
        ans_cy = _PAD + (max_layer + 1) * (_NH + _VGAP) + _ANS_H // 2

        for nid in answer_nids:
            if nid in pos:
                x1, y1 = pos[nid]
                parts.append(
                    f'<line x1="{x1}" y1="{y1 + _NH // 2}" '
                    f'x2="{ans_cx}" y2="{ans_cy - _ANS_H // 2}" '
                    f'stroke="#fbbf24" stroke-width="1.5" stroke-dasharray="4,3" '
                    f'marker-end="url(#arr)"/>'
                )

        parts += [
            f'<rect x="{ans_cx - _ANS_W // 2}" y="{ans_cy - _ANS_H // 2}" '
            f'width="{_ANS_W}" height="{_ANS_H}" rx="{_ANS_H // 2}" '
            f'fill="#fef3c7" stroke="#fbbf24" stroke-width="1.5"/>',
            f'<text x="{ans_cx}" y="{ans_cy + 4}" text-anchor="middle" '
            f'fill="#92400e" font-size="10" font-weight="600">ANSWER</text>',
        ]
        # Extend SVG height to fit the ANSWER node
        svg_h_with_ans = ans_cy + _ANS_H // 2 + _PAD
        # Patch the opening <svg> tag height
        parts[0] = parts[0].replace(f'height="{svg_h}"', f'height="{svg_h_with_ans}"')

    parts.append("</svg>")
    return "\n".join(parts), ordered_ids
