"""Phase 2 / 3 — NiceGUI report dashboard for FileOrganiser DAG.

Run from code/:
    .venv\\Scripts\\python.exe ui/app.py
then open http://localhost:8110
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from nicegui import ui

from . import dag_svg, session as sess
from .session import (
    classified_items,
    extract_scan,
    group_by_destination,
    list_sessions,
    load_session,
    pattern_analysis,
    sensitive_files,
    session_stats,
)
from .widgets import CATEGORY_COLOR, conf_bar, file_row, stat_card

ROOT = Path(__file__).parent.parent
APP_PORT = 8110

# ── Warm design system ────────────────────────────────────────────────────────
# Injected before any page renders. Overrides Quasar cold-gray defaults with
# the parchment palette from file_organizer_explainer.html.
ui.add_head_html("""
<style>
:root {
  --fo-bg:        #f9f8f4;
  --fo-bg2:       #f1efe9;
  --fo-bg3:       #e8e6de;
  --fo-text:      #2c2c2a;
  --fo-text2:     #5f5e5a;
  --fo-text3:     #888780;
  --fo-bd:        rgba(0,0,0,0.10);
  --fo-radius:    10px;
  --fo-shadow:    0 1px 4px rgba(0,0,0,0.07);
  --fo-info:      #185fa5;
  --fo-info-bg:   #e6f1fb;
  --fo-info-bd:   #b5d4f4;
  --fo-ok:        #3b6d11;
  --fo-ok-bg:     #eaf3de;
  --fo-warn:      #854f0b;
  --fo-warn-bg:   #faeeda;
  --fo-danger:    #993c1d;
  --fo-danger-bg: #faece7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fo-bg:        #1e1e1c;
    --fo-bg2:       #282825;
    --fo-bg3:       #323230;
    --fo-text:      #e8e6de;
    --fo-text2:     #b4b2a9;
    --fo-text3:     #888780;
    --fo-bd:        rgba(255,255,255,0.09);
    --fo-shadow:    0 1px 4px rgba(0,0,0,0.30);
    --fo-info:      #85b7eb;
    --fo-info-bg:   #042c53;
    --fo-info-bd:   #0c447c;
    --fo-ok:        #97c459;
    --fo-ok-bg:     #173404;
    --fo-warn:      #ef9f27;
    --fo-warn-bg:   #412402;
    --fo-danger:    #f0997b;
    --fo-danger-bg: #4a1b0c;
  }
}

/* ── Global ── */
body, .q-page-container, .q-page {
  background: var(--fo-bg) !important;
  color: var(--fo-text) !important;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}

/* ── Header ── */
.q-header {
  background: var(--fo-bg2) !important;
  border-bottom: 1px solid var(--fo-bd) !important;
  box-shadow: var(--fo-shadow) !important;
  color: var(--fo-text) !important;
}

/* ── Cards ── */
.q-card {
  background: var(--fo-bg2) !important;
  border: 1px solid var(--fo-bd) !important;
  border-radius: var(--fo-radius) !important;
  box-shadow: var(--fo-shadow) !important;
}

/* ── Tabs ── */
.q-tabs { background: transparent !important; }
.q-tab  { color: var(--fo-text2) !important; font-size: 13px !important; font-weight: 500 !important; }
.q-tab--active { color: var(--fo-info) !important; font-weight: 600 !important; }
.q-tab__indicator { background: var(--fo-info) !important; height: 2px !important; }
.q-tab-panels { background: transparent !important; }
.q-tab-panel  { padding: 0 !important; background: transparent !important; }

/* ── Expansion items ── */
.q-expansion-item > .q-expansion-item__container > .q-item {
  background: var(--fo-bg3) !important;
  border-radius: 7px !important;
  border: 1px solid var(--fo-bd) !important;
  padding: 6px 12px !important;
  font-size: 13px !important;
  color: var(--fo-text2) !important;
  min-height: 36px !important;
}
.q-expansion-item__content { background: transparent !important; }

/* ── Badges ── */
.q-badge {
  font-size: 11px !important;
  padding: 2px 7px !important;
  border-radius: 5px !important;
  font-weight: 500 !important;
  letter-spacing: 0.01em !important;
}

/* ── Separator ── */
.q-separator { background: var(--fo-bd) !important; opacity: 1 !important; }

/* ── Input / Select ── */
.q-field__control { background: var(--fo-bg2) !important; border-radius: 8px !important; }
.q-field__native, .q-field__prefix { color: var(--fo-text) !important; }
.q-field__label { color: var(--fo-text2) !important; font-size: 13px !important; }
.q-field--outlined .q-field__control:before { border-color: var(--fo-bd) !important; }
.q-menu { background: var(--fo-bg2) !important; border: 1px solid var(--fo-bd) !important; }
.q-item { color: var(--fo-text) !important; font-size: 13px !important; }
.q-item:hover { background: var(--fo-bg3) !important; }

/* ── Buttons ── */
.q-btn { border-radius: 8px !important; font-size: 13px !important; font-weight: 500 !important; letter-spacing: 0.01em !important; }

/* ── Progress bar ── */
.q-linear-progress { border-radius: 3px !important; }
.q-linear-progress__track { background: var(--fo-bg3) !important; opacity: 1 !important; }

/* ── Code / pre ── */
.q-code, pre, .nicegui-code { background: var(--fo-bg3) !important; border-radius: 7px !important; font-size: 12px !important; border: 1px solid var(--fo-bd) !important; }

/* ── Tailwind text-gray overrides ── */
.text-gray-800 { color: var(--fo-text)  !important; }
.text-gray-700 { color: var(--fo-text)  !important; }
.text-gray-600 { color: var(--fo-text2) !important; }
.text-gray-500 { color: var(--fo-text2) !important; }
.text-gray-400 { color: var(--fo-text3) !important; }

/* ── Stat card number ── */
.text-2xl.font-bold { font-size: 22px !important; color: var(--fo-text) !important; }

/* ── Notification (toast) ── */
.q-notification { background: var(--fo-bg2) !important; color: var(--fo-text) !important; border: 1px solid var(--fo-bd) !important; border-radius: 8px !important; box-shadow: var(--fo-shadow) !important; }

/* ── Switch ── */
.q-toggle__track { background: var(--fo-bg3) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--fo-bg2); }
::-webkit-scrollbar-thumb { background: var(--fo-bd); border-radius: 3px; }
</style>
""", shared=True)

# ── scan_config helpers ───────────────────────────────────────────────────────
# Import scanner's config I/O so Lock toggles can persist to scan_config.yaml
sys.path.insert(0, str(ROOT))
from scanner import _load_scan_config, _save_scan_config  # noqa: E402


def _toggle_locked_zone(path: str, add: bool) -> None:
    """Add or remove *path* from locked_zones in scan_config.yaml."""
    cfg = _load_scan_config()
    zones: list[str] = list(cfg.get("locked_zones", []))
    if add and path not in zones:
        zones.append(path)
    elif not add and path in zones:
        zones.remove(path)
    cfg["locked_zones"] = zones
    try:
        _save_scan_config(cfg)
    except Exception as exc:
        ui.notify(f"Could not save scan_config.yaml: {exc}", type="warning")


# ── Dashboard tab ─────────────────────────────────────────────────────────────

def render_dashboard(session: dict, locked_zones: set[str]) -> None:
    scan     = extract_scan(session["query"])
    classed  = classified_items(session)
    private  = sensitive_files(session)
    pattern  = pattern_analysis(session)
    stats    = session_stats(session)
    dup_groups = scan.get("duplicate_groups", [])
    skipped    = scan.get("skipped_folders", [])

    # ── Summary cards ──────────────────────────────────────────────────────
    with ui.row().classes("gap-4 flex-wrap mb-5"):
        stat_card("Files scanned",    str(stats["file_count"]), "description",   "blue")
        stat_card("Private flagged",  str(stats["sensitive"]),  "lock",           "red")
        stat_card("Dup groups",       str(stats["dup_groups"]), "content_copy",   "orange")
        stat_card("Skipped folders",  str(stats["skipped"]),    "folder_off",     "grey")
        if pattern:
            effort = (pattern.get("plans") or {}).get("medium", {}).get("effort", "")
            stat_card("Recommended effort", effort or "—", "schedule", "green")

    # ── Execution DAG ──────────────────────────────────────────────────────
    # overflow-x:auto overrides Quasar q-card's default overflow:hidden so
    # wide graphs scroll instead of being clipped.
    with ui.card().classes("w-full mb-5 shadow-sm").style("overflow-x:auto"):
        ui.label("Execution Graph (DAG)").classes("text-sm font-semibold text-gray-500 mb-2")
        ui.label("Click a node to inspect its prompt and output.").classes(
            "text-xs text-gray-400 mb-3"
        )

        svg_str, _ordered_ids = dag_svg.build(session)

        # detail_ref[0] will be set to the column element after SVG is laid out.
        # _show_detail reads it lazily so order of NiceGUI element creation
        # does not matter — only the order of DOM placement matters.
        detail_ref: list = [None]

        def _show_uq_detail() -> None:
            col = detail_ref[0]
            if col is None:
                return
            col.clear()
            col.style("display:block")
            query_raw = session.get("query", "")
            # Separate human-readable prefix from SCAN_RESULT blob
            m = re.search(r"SCAN_RESULT:", query_raw)
            human_part = query_raw[:m.start()].strip() if m else query_raw.strip()
            has_scan = m is not None
            with col:
                ui.label("User Query").classes(
                    "font-mono text-sm font-semibold text-gray-700 mb-2"
                )
                if human_part:
                    ui.label(human_part).classes(
                        "text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 "
                        "p-3 rounded border border-gray-100 mb-2"
                    )
                if has_scan:
                    ui.label(
                        "+ SCAN_RESULT payload attached (file manifest, hashes, "
                        "duplicate groups — not shown here for brevity)"
                    ).classes("text-xs text-gray-400 italic")

        def _show_edge_detail(src_nid: str, tgt_nid: str) -> None:
            col = detail_ref[0]
            if col is None:
                return
            col.clear()
            col.style("display:block")
            src = session["nodes"].get(src_nid, {})
            tgt = session["nodes"].get(tgt_nid, {})
            src_skill = src.get("skill", src_nid)
            tgt_skill = tgt.get("skill", tgt_nid)
            with col:
                ui.label(
                    f"{src_skill} ({src_nid})  →  {tgt_skill} ({tgt_nid})"
                ).classes("font-mono text-sm font-semibold text-gray-700 mb-1")
                ui.label(
                    "This edge means the target node declared the source in its "
                    "inputs list and received its output as context."
                ).classes("text-xs text-gray-400 mb-3")

                src_out = (src.get("result") or {}).get("output")
                if src_out is not None:
                    label = f"Data produced by {src_skill} (flows into {tgt_skill})"
                    with ui.expansion(label, value=True).classes("w-full"):
                        ui.code(
                            json.dumps(src_out, indent=2, default=str)[:2000],
                            language="json",
                        ).classes("text-xs w-full")
                else:
                    ui.label(f"No output recorded for {src_nid}.").classes(
                        "text-xs text-gray-400"
                    )

        def _show_detail(nid: str) -> None:
            col = detail_ref[0]
            if col is None:
                return
            col.clear()
            col.style("display:block")
            node_data = session["nodes"].get(nid)
            if not node_data:
                with col:
                    ui.label(f"No persisted data for {nid}.").classes(
                        "text-xs text-gray-400"
                    )
                return
            result = node_data.get("result") or {}
            with col:
                # Header row
                status = node_data.get("status", "?")
                status_color = {
                    "complete": "green", "failed": "red",
                    "skipped": "grey", "running": "blue",
                }.get(status, "grey")
                with ui.row().classes("items-center gap-3 mb-2 flex-wrap"):
                    ui.label(
                        f"{node_data.get('skill', '?')}  ·  {nid}"
                    ).classes("font-mono text-sm font-semibold text-gray-700")
                    ui.badge(status, color=status_color)
                    t_start = node_data.get("started_at")
                    t_end   = node_data.get("completed_at")
                    if t_start and t_end:
                        ui.label(f"{t_end - t_start:.1f}s").classes(
                            "text-xs text-gray-400"
                        )

                # Inputs
                inputs = node_data.get("inputs") or []
                if inputs:
                    ui.label(
                        "Inputs: " + ", ".join(inputs)
                    ).classes("text-xs text-gray-500 mb-1")

                # Error
                err = result.get("error") if isinstance(result, dict) else None
                if err and isinstance(err, str):
                    with ui.card().classes(
                        "w-full bg-red-50 border border-red-200 p-2 mb-2"
                    ):
                        ui.label("Error").classes(
                            "text-xs font-semibold text-red-600 mb-1"
                        )
                        ui.label(str(err)[:800]).classes(
                            "text-xs font-mono text-red-700 whitespace-pre-wrap"
                        )

                # Result output — show whenever the field is present, even if {}
                output = result.get("output") if isinstance(result, dict) else None
                if output is not None:
                    label = "Result output" if output else "Result output (empty)"
                    with ui.expansion(label, value=False).classes("w-full mb-2"):
                        ui.code(
                            json.dumps(output, indent=2, default=str)[:2000],
                            language="json",
                        ).classes("text-xs w-full")

                # Prompt sent
                prompt = node_data.get("prompt_sent")
                if prompt:
                    with ui.expansion("Prompt sent to LLM", value=False).classes("w-full"):
                        ui.label(prompt[:3000]).classes(
                            "text-xs font-mono text-gray-600 whitespace-pre-wrap "
                            "bg-gray-50 p-2 rounded"
                        )

        # js_handler runs client-side: walk from the click target up to the
        # nearest <g data-nid="..."> and call emit() to send the id to Python.
        # emit() is NiceGUI's socket.io send function injected into the closure.
        # Clicking empty space finds no [data-nid] and emits nothing.
        svg_el = ui.html(
            f'<div style="overflow-x:auto;padding-bottom:4px;">'
            f'{svg_str}'
            f'</div>'
        )

        def _on_node_click(e) -> None:
            if not e.args:
                return
            raw = e.args[0] if isinstance(e.args, list) else e.args
            try:
                val = json.loads(raw) if isinstance(raw, str) else str(raw)
            except Exception:
                val = str(raw).strip('"')
            if not val:
                return
            # Edge clicks are encoded as "__EDGE__src::tgt"
            if val == "__UQ__":
                _show_uq_detail()
            elif val.startswith("__EDGE__"):
                payload = val[len("__EDGE__"):]
                if "::" in payload:
                    src, tgt = payload.split("::", 1)
                    _show_edge_detail(src, tgt)
            else:
                _show_detail(val)

        svg_el.on(
            'click',
            _on_node_click,
            js_handler=(
                "(e) => {"
                # ── clear previous node highlight ─────────────────────────
                "  var prev = document.querySelector('[data-dag-sel]');"
                "  if (prev) {"
                "    var pr = prev.querySelector('rect');"
                "    if (pr) {"
                "      pr.setAttribute('stroke', prev.dataset.origStroke || 'rgba(255,255,255,0.25)');"
                "      pr.setAttribute('stroke-width', prev.dataset.origSw || '1.2');"
                "      pr.style.filter = '';"
                "    }"
                "    delete prev.dataset.dagSel;"
                "  }"
                # ── clear previous edge highlight ─────────────────────────
                "  var prevEdge = document.querySelector('[data-dag-edge-sel]');"
                "  if (prevEdge) {"
                "    var pe = prevEdge.querySelector('.dag-edge-vis');"
                "    if (pe) { pe.setAttribute('stroke','#cbd5e1'); pe.setAttribute('stroke-width','1.5'); }"
                "    delete prevEdge.dataset.dagEdgeSel;"
                "  }"
                # ── check if a node was clicked ───────────────────────────
                "  var g = e.target.closest('[data-nid]');"
                "  if (g) {"
                "    var rect = g.querySelector('rect');"
                "    if (rect) {"
                "      if (!g.dataset.origStroke) g.dataset.origStroke = rect.getAttribute('stroke');"
                "      if (!g.dataset.origSw)     g.dataset.origSw     = rect.getAttribute('stroke-width');"
                "      g.dataset.dagSel = '1';"
                "      rect.setAttribute('stroke','#fff');"
                "      rect.setAttribute('stroke-width','3');"
                "      rect.style.filter = 'drop-shadow(0 0 6px rgba(255,255,255,0.85))';"
                "    }"
                "    emit(g.dataset.nid);"
                "    return;"
                "  }"
                # ── check if the USER QUERY pill was clicked ──────────────
                "  var uq = e.target.closest('[data-uq]');"
                "  if (uq) { emit('__UQ__'); return; }"
                # ── check if a real edge was clicked ──────────────────────
                "  var eg = e.target.closest('[data-esrc]');"
                "  if (eg) {"
                "    var el = eg.querySelector('.dag-edge-vis');"
                "    if (el) { el.setAttribute('stroke','#60a5fa'); el.setAttribute('stroke-width','2.5'); }"
                "    eg.dataset.dagEdgeSel = '1';"
                "    emit('__EDGE__' + eg.dataset.esrc + '::' + eg.dataset.etgt);"
                "  }"
                "}"
            ),
        )

        # Legend
        ui.html(
            '<div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap;">'
            '<span style="font-size:11px;color:#6b7280;display:flex;align-items:center;gap:5px;">'
            '<svg width="28" height="10"><line x1="0" y1="5" x2="28" y2="5" '
            'stroke="#cbd5e1" stroke-width="1.5" marker-end="url(#arr)"/></svg>'
            'data-dependency edge (click to see what flows through)</span>'
            '<span style="font-size:11px;color:#6b7280;display:flex;align-items:center;gap:5px;">'
            '<svg width="28" height="10"><line x1="0" y1="5" x2="28" y2="5" '
            'stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4,3"/></svg>'
            'conceptual link to USER QUERY / ANSWER (virtual, not a runtime edge)</span>'
            '<span style="font-size:11px;color:#6b7280;display:flex;align-items:center;gap:5px;">'
            '<svg width="14" height="14"><rect x="1" y="1" width="12" height="12" rx="2" '
            'fill="none" stroke="#fbbf24" stroke-width="2"/></svg>'
            'node that produced the final answer</span>'
            '</div>'
        )

        # Detail panel rendered AFTER the SVG so it appears below it in DOM.
        detail_ref[0] = (
            ui.column()
            .classes("w-full mt-3 border-t border-gray-100 pt-3")
            .style("display:none")
        )

    # ── Already-organised highlights ───────────────────────────────────────
    if pattern and pattern.get("highlights"):
        with ui.card().classes("w-full mb-5 shadow-sm border-l-4 border-green-400"):
            with ui.row().classes("items-center gap-2 mb-3"):
                ui.icon("verified", color="green")
                ui.label("Already well-organised — left untouched").classes(
                    "text-sm font-semibold text-green-700"
                )
            for h in pattern["highlights"]:
                path  = h.get("path", "")
                score = h.get("score", 0)
                note  = h.get("note", "")
                badge_txt = h.get("label", "")

                with ui.row().classes("items-center gap-3 py-1.5 border-b border-green-100"):
                    ui.icon("folder", color="green")
                    with ui.column().classes("flex-1 gap-0.5"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(path).classes("font-mono text-sm font-semibold")
                            ui.badge(badge_txt, color="green").classes("text-xs")
                        ui.label(note).classes("text-xs text-gray-500")
                        conf_bar(score)
                    ui.switch(
                        "Lock",
                        value=(path in locked_zones),
                        on_change=lambda e, p=path: (
                            locked_zones.add(p) if e.value else locked_zones.discard(p),
                            _toggle_locked_zone(p, e.value),
                        ),
                    ).props("dense color=green")

    # ── Classified findings ────────────────────────────────────────────────
    if classed:
        with ui.card().classes("w-full mb-5 shadow-sm"):
            ui.label("Classified Files — Grouped by Destination").classes(
                "text-sm font-semibold text-gray-600 mb-2"
            )
            groups = group_by_destination(classed)
            for dest in sorted(groups):
                if any(dest.startswith(lz) for lz in locked_zones):
                    continue
                items    = groups[dest]
                avg_conf = int(sum(i.get("confidence", 80) for i in items) / len(items))
                needs_rv = any(i.get("needs_review") for i in items)

                icon_name  = "warning" if needs_rv else "check_circle"
                count_txt  = f"{len(items)} file{'s' if len(items) > 1 else ''}"

                with ui.expansion(
                    f"{dest}  ({count_txt})", icon=icon_name
                ).props("header-class='text-sm font-medium'").classes("w-full"):
                    with ui.column().classes("gap-1 w-full px-1 pb-1"):
                        conf_bar(avg_conf)
                        for item in sorted(items, key=lambda x: -x.get("confidence", 0)):
                            file_row(item)

    # ── Private / sensitive ────────────────────────────────────────────────
    if private:
        with ui.card().classes("w-full mb-5 shadow-sm border-l-4 border-red-400"):
            with ui.row().classes("items-center gap-2 mb-2"):
                ui.icon("lock", color="red")
                ui.label("Private / Sensitive Files").classes(
                    "text-sm font-semibold text-red-700"
                )
                ui.badge("metadata only — content never read", color="red").classes("text-xs")
            for item in private:
                with ui.row().classes(
                    "items-center gap-3 py-1.5 border-b border-red-100 w-full"
                ):
                    ui.label(item.get("name", "?")).classes("font-mono text-sm flex-1")
                    ui.badge(item.get("suggestion", "Private"), color="red").classes("text-xs")
                    ui.label(f"{item.get('confidence', 90)}%").classes(
                        "text-xs text-gray-400 w-9 text-right"
                    )

    # ── Duplicate groups ───────────────────────────────────────────────────
    if dup_groups:
        with ui.card().classes("w-full mb-5 shadow-sm"):
            ui.label(
                f"Duplicate Groups ({len(dup_groups)}) — safe to delete one copy each"
            ).classes("text-sm font-semibold text-gray-600 mb-2")
            for g in dup_groups:
                paths = g.get("paths", [])
                with ui.expansion(
                    f"Hash {g['hash'][:12]}…  ×{len(paths)} copies"
                ).classes("w-full"):
                    for p in paths:
                        ui.label(p).classes("font-mono text-xs text-gray-600 px-2 py-0.5")

    # ── Skipped folders ────────────────────────────────────────────────────
    if skipped:
        with ui.card().classes("w-full mb-5 shadow-sm"):
            ui.label("Skipped Folders (recognised at boundary, not descended)").classes(
                "text-sm font-semibold text-gray-600 mb-2"
            )
            for s in skipped:
                with ui.row().classes("items-center gap-2 text-xs text-gray-500 py-1"):
                    ui.icon("folder_off", size="xs")
                    ui.label(s.get("path", "")).classes("font-mono")
                    ui.label(f"({s.get('file_count', '?')} files)").classes("text-gray-400")
                    ui.label(s.get("reason", "")).classes("italic text-gray-400")

    # ── Action row ─────────────────────────────────────────────────────────
    ui.separator().classes("my-4")
    with ui.row().classes("gap-3 flex-wrap"):
        ui.button("Approve Medium Plan", icon="check_circle", color="green",
                  on_click=lambda: _dlg_approve(session))
        ui.button("Refine selected",     icon="refresh",       color="blue",
                  on_click=lambda: _dlg_refine(session))
        ui.button("Help me choose",      icon="help_outline",  color="grey",
                  on_click=lambda: _dlg_nl_help(session))


# ── Compare Plans tab ─────────────────────────────────────────────────────────

def render_compare_plans(session: dict) -> None:
    pattern = pattern_analysis(session)
    if not pattern or "plans" not in pattern:
        ui.label("No plan data available for this session.").classes(
            "text-gray-400 text-sm mt-8"
        )
        return

    plans = pattern.get("plans", {})

    with ui.row().classes("gap-4 w-full flex-wrap items-start"):
        for tier in ("minimal", "medium", "best"):
            p = plans.get(tier)
            if not p:
                continue
            recommended = p.get("recommended", False)
            border = "border-2 border-green-400" if recommended else ""
            with ui.card().classes(f"flex-1 min-w-[210px] max-w-sm {border} shadow-sm"):
                with ui.row().classes("items-center gap-2 mb-1"):
                    ui.label(tier.capitalize()).classes("font-bold text-base")
                    if recommended:
                        ui.badge("Recommended", color="green")
                with ui.row().classes("gap-4 text-xs text-gray-500 mb-3 flex-wrap"):
                    ui.label(f"⏱ {p.get('effort', '?')}")
                    ui.label(f"📦 {p.get('reclaimable', '?')}")
                    ui.label(f"⚠ risk: {p.get('risk', '?').replace('_', ' ')}")
                for action in p.get("actions", []):
                    with ui.row().classes("items-start gap-1 mb-2"):
                        ui.label("•").classes("text-gray-400 text-xs mt-0.5 shrink-0")
                        ui.label(action).classes("text-xs text-gray-700")

    # Cumulative diff
    ui.separator().classes("my-5")
    ui.label("Cumulative diff — what each tier adds over the previous").classes(
        "text-xs text-gray-500 mb-3"
    )
    minimal_acts = set(plans.get("minimal", {}).get("actions", []))
    medium_acts  = set(plans.get("medium",  {}).get("actions", []))
    best_acts    = set(plans.get("best",    {}).get("actions", []))

    with ui.card().classes("w-full shadow-sm"):
        ui.label("Medium adds over Minimal:").classes(
            "text-xs font-semibold text-blue-600 mb-1"
        )
        added = medium_acts - minimal_acts
        for a in sorted(added) or ["(no additions)"]:
            ui.label(f"+ {a}").classes("text-xs text-blue-700 font-mono pl-3 py-0.5")

        ui.separator().classes("my-3")
        ui.label("Best adds over Medium:").classes(
            "text-xs font-semibold text-violet-600 mb-1"
        )
        added = best_acts - medium_acts
        for a in sorted(added) or ["(no additions)"]:
            ui.label(f"+ {a}").classes("text-xs text-violet-700 font-mono pl-3 py-0.5")


# ── Filter Files tab ──────────────────────────────────────────────────────────

def render_filters(session: dict) -> None:
    classed = classified_items(session)
    private = sensitive_files(session)

    all_items = list(classed) + [
        {
            "name":        f.get("name", "?"),
            "category":    "private",
            "destination": f.get("suggestion", "Private"),
            "confidence":  f.get("confidence", 90),
            "reason":      f.get("reason", "sensitive — metadata only"),
            "needs_review": False,
        }
        for f in private
    ]

    all_categories   = sorted({i.get("category", "other") for i in all_items})
    all_destinations = sorted({i.get("destination", "?")    for i in all_items})

    state: dict = {"category": None, "dest": None, "min_conf": 0, "nl": ""}
    results_col = ui.column().classes("w-full gap-2 mt-4")

    def _apply() -> None:
        items = all_items
        if state["category"]:
            items = [i for i in items if i.get("category") == state["category"]]
        if state["dest"]:
            items = [i for i in items if i.get("destination") == state["dest"]]
        if state["min_conf"]:
            items = [i for i in items if i.get("confidence", 0) >= state["min_conf"]]
        if state["nl"]:
            q = state["nl"].lower()
            items = [
                i for i in items
                if q in (
                    i.get("name", "") + " " +
                    i.get("reason", "") + " " +
                    i.get("destination", "")
                ).lower()
            ]
        items = sorted(items, key=lambda x: -x.get("confidence", 0))

        results_col.clear()
        with results_col:
            if not items:
                ui.label("No files match the current filters.").classes(
                    "text-gray-400 text-sm"
                )
                return
            ui.label(f"{len(items)} file(s) matched").classes("text-xs text-gray-400 mb-1")
            for item in items:
                cat    = item.get("category", "other")
                conf   = item.get("confidence", 0)
                review = item.get("needs_review", False)
                with ui.card().classes("w-full p-2 shadow-sm"):
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(item.get("name", "?")).classes("font-mono text-sm flex-1")
                        ui.badge(cat, color=CATEGORY_COLOR.get(cat, "grey")).classes("text-xs")
                        if review:
                            ui.badge("needs your eyes", color="orange").classes("text-xs")
                        ui.label(f"→ {item.get('destination', '?')}").classes(
                            "text-xs text-gray-500"
                        )
                        ui.label(f"{conf}%").classes("text-xs text-gray-400")
                    ui.label(item.get("reason", "")).classes("text-xs text-gray-400 pl-1")

    # Tier 1 — Structured
    with ui.card().classes("w-full shadow-sm mb-2"):
        ui.label("Structured Filters").classes("text-xs font-semibold text-gray-500 mb-2")
        with ui.row().classes("gap-4 flex-wrap items-end"):
            ui.select(
                ["All"] + all_categories, label="Category", value="All",
                on_change=lambda e: (
                    state.update({"category": None if e.value == "All" else e.value}),
                    _apply(),
                ),
            ).classes("min-w-[140px]")
            ui.select(
                ["All"] + all_destinations, label="Destination", value="All",
                on_change=lambda e: (
                    state.update({"dest": None if e.value == "All" else e.value}),
                    _apply(),
                ),
            ).classes("min-w-[220px]")
            with ui.column().classes("gap-0"):
                ui.label("Min confidence").classes("text-xs text-gray-400")
                ui.slider(
                    min=0, max=100, step=5, value=0,
                    on_change=lambda e: (state.update({"min_conf": int(e.value)}), _apply()),
                ).classes("w-44")

    # Tier 2 — Semantic combobox
    with ui.card().classes("w-full shadow-sm mb-2"):
        ui.label("Semantic Label — search destinations").classes(
            "text-xs font-semibold text-gray-500 mb-2"
        )
        ui.select(
            options=all_destinations,
            label="Destination (type to filter)",
            value=None,
            with_input=True,
            clearable=True,
            on_change=lambda e: (state.update({"dest": e.value or None}), _apply()),
        ).classes("w-full")

    # Tier 3 — Natural language
    with ui.card().classes("w-full shadow-sm mb-2"):
        ui.label("Just ask").classes("text-xs font-semibold text-gray-500 mb-1")
        ui.label(
            'e.g. "receipts", "low confidence", "Documents"'
        ).classes("text-xs text-gray-400 mb-2")
        nl_inp = ui.input(placeholder="ask in plain language…").classes("w-full")

        with ui.row().classes("mt-1 gap-2"):
            ui.button("Search", icon="search",
                      on_click=lambda: (state.update({"nl": nl_inp.value.strip()}), _apply()))
            ui.button("Clear", icon="clear", color="grey",
                      on_click=lambda: (
                          nl_inp.set_value(""),
                          state.update({"nl": ""}),
                          _apply(),
                      ))

    _apply()


# ── History tab ───────────────────────────────────────────────────────────────

def render_history(sessions: list[str]) -> None:
    ui.label("All Sessions").classes("text-sm font-semibold text-gray-600 mb-3")
    if not sessions:
        ui.label("No sessions found.").classes("text-gray-400 text-sm")
        return

    sess_dir = Path(__file__).parent.parent / "state" / "sessions"
    with ui.column().classes("w-full gap-2"):
        for sid in sessions:
            base = sess_dir / sid
            nodes_dir = base / "nodes"
            node_files = list(nodes_dir.glob("n_*.json")) if nodes_dir.exists() else []
            node_count  = len(node_files)
            has_formatter = False
            if node_count:
                for f in node_files:
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        if d.get("skill") == "formatter" and d.get("status") == "complete":
                            has_formatter = True
                            break
                    except (json.JSONDecodeError, KeyError):
                        pass

            with ui.card().classes("w-full p-3 shadow-sm"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon(
                        "check_circle" if has_formatter else "pending",
                        color="green" if has_formatter else "orange",
                    )
                    ui.label(sid).classes("font-mono text-sm font-semibold flex-1")
                    ui.label(f"{node_count} node file(s)").classes("text-xs text-gray-400")


# ── Action dialogs ────────────────────────────────────────────────────────────

def _build_move_ops(session: dict):
    """Build MoveOp list from classified items + scan root.

    Returns (ops, warnings) where warnings is a list of names that
    couldn't be resolved to an on-disk path.
    """
    from executor import MoveOp

    scan      = extract_scan(session["query"])
    scan_root = scan.get("root", "")
    if not scan_root:
        return [], ["No scan root found in session — cannot build move list."]

    # Build name → relative-path lookup from scan result
    name_to_rel: dict[str, str] = {}
    for f in scan.get("files", []):
        name_to_rel.setdefault(f["name"], f["path"])

    classed  = classified_items(session)
    ops: list[MoveOp] = []
    warnings: list[str] = []

    for item in classed:
        name = item.get("name", "")
        dest = item.get("destination", "")
        if not name or not dest:
            continue
        if name not in name_to_rel:
            warnings.append(f"{name}: not found in scan manifest — skipped")
            continue
        src = Path(scan_root) / name_to_rel[name]
        dst = Path(scan_root) / dest / name
        if src == dst:
            continue  # already at destination
        ops.append(MoveOp(src=src, dst=dst, reason=item.get("reason", "")))

    return ops, warnings


def _dlg_approve(session: dict) -> None:
    """Full Phase-3 flow: dry-run → confirm dialog → apply → undo button."""
    from executor import MoveExecutor

    ops, build_warnings = _build_move_ops(session)

    with ui.dialog() as dlg, ui.card().classes("w-[560px] max-h-[85vh] overflow-y-auto"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("check_circle", color="green", size="lg")
            ui.label("Approve Medium Plan").classes("text-lg font-bold")

        if not ops:
            ui.label(
                "No file moves to execute for this session."
            ).classes("text-sm text-gray-500")
            if build_warnings:
                for w in build_warnings:
                    ui.label(f"⚠ {w}").classes("text-xs text-amber-700")
            ui.button("Close", on_click=dlg.close).classes("mt-3")
            dlg.open()
            return

        executor = MoveExecutor(ops, sid=session["sid"])
        report   = executor.dry_run()

        # ── dry-run report ─────────────────────────────────────────────────
        ui.label(
            f"Dry-run: {len(report.ops)} move(s) planned, "
            f"{len(report.conflicts)} conflict(s)"
        ).classes("text-sm font-semibold text-gray-700 mb-2")

        if report.reclaimable_bytes:
            mb = report.reclaimable_bytes / (1024 * 1024)
            ui.label(
                f"♻ {mb:.1f} MB reclaimable (identical files already at destination)"
            ).classes("text-xs text-green-700 mb-2")

        if report.conflicts:
            with ui.card().classes("w-full bg-red-50 border border-red-200 mb-3 p-2"):
                ui.label(f"{len(report.conflicts)} Conflict(s) — must resolve before executing").classes(
                    "text-xs font-semibold text-red-700 mb-1"
                )
                for c in report.conflicts[:10]:
                    ui.label(
                        f"[{c.kind}] {Path(c.src).name} → {Path(c.dst).name}: {c.detail}"
                    ).classes("text-xs text-red-600 font-mono py-0.5")
                if len(report.conflicts) > 10:
                    ui.label(f"… {len(report.conflicts) - 10} more").classes("text-xs text-red-400")

        # Preview of ops (first 15)
        with ui.expansion(f"Preview moves ({len(report.ops)} total)", value=False).classes("w-full mb-3"):
            for op in report.ops[:15]:
                ui.label(
                    f"{op.src.name}  →  {op.dst.parent.name}/{op.dst.name}"
                ).classes("text-xs font-mono text-gray-600 py-0.5")
            if len(report.ops) > 15:
                ui.label(f"… {len(report.ops) - 15} more").classes("text-xs text-gray-400")

        if build_warnings:
            with ui.expansion(f"{len(build_warnings)} file(s) skipped", value=False).classes("w-full mb-3"):
                for w in build_warnings:
                    ui.label(f"⚠ {w}").classes("text-xs text-amber-700 py-0.5")

        ui.separator().classes("my-2")

        # undo log reference for the callback
        undo_state: dict = {"log": None}
        status_lbl  = ui.label("").classes("text-sm text-gray-600 mt-2")
        undo_btn    = ui.button("Undo last apply", icon="undo", color="orange").classes("mt-2 hidden")

        async def _do_undo() -> None:
            from executor import MoveExecutor
            log = undo_state.get("log")
            if not log:
                ui.notify("No undo log available.", type="warning")
                return
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: MoveExecutor.undo(log)
                )
                ui.notify("Undo complete — files restored.", type="positive")
                undo_btn.classes(add="hidden")
                status_lbl.set_text("Undo complete. Files restored to original locations.")
            except Exception as exc:
                ui.notify(f"Undo failed: {exc}", type="negative")

        undo_btn.on_click(_do_undo)

        async def _do_apply() -> None:
            execute_btn.disable()
            status_lbl.set_text("Applying moves…")
            try:
                log = await asyncio.get_event_loop().run_in_executor(
                    None, executor.apply
                )
                undo_state["log"] = log
                moved = len(log.moves)
                status_lbl.set_text(
                    f"Done — {moved} file(s) moved. "
                    f"Undo log: state/undo_{session['sid']}.json"
                )
                undo_btn.classes(remove="hidden")
                ui.notify(f"{moved} file(s) moved successfully.", type="positive")
            except Exception as exc:
                status_lbl.set_text(f"Error: {exc}")
                ui.notify(f"Apply failed: {exc}", type="negative")
                execute_btn.enable()

        with ui.row().classes("gap-2 mt-2"):
            execute_btn = ui.button(
                "Execute moves",
                icon="send",
                color="green" if report.is_clean() else "grey",
                on_click=_do_apply,
            )
            if not report.is_clean():
                execute_btn.disable()
                ui.label("Resolve conflicts first").classes("text-xs text-red-500 self-center")
            ui.button("Cancel", on_click=dlg.close)

    dlg.open()


def _dlg_refine(session: dict) -> None:
    with ui.dialog() as dlg, ui.card().classes("w-[500px]"):
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.icon("refresh", color="blue", size="lg")
            ui.label("Refine Plan").classes("text-lg font-bold")
        ui.label(
            "Describe what to change. The engine will re-plan only the affected "
            "sub-graph; cached branches stay as-is."
        ).classes("text-sm text-gray-500 mb-3")
        inp = ui.textarea(
            placeholder=(
                'e.g. "never move files from Projects/"\n'
                '"route IMG_20260601_165420.txt to Documents/Notes"'
            ),
        ).classes("w-full")

        async def _do_refine() -> None:
            instruction = (inp.value or "").strip()
            if not instruction:
                ui.notify("Please enter a refinement instruction.", type="warning")
                return
            dlg.close()
            await _run_refine(session, instruction)

        with ui.row().classes("mt-3 gap-2"):
            ui.button("Refine", icon="send", color="blue", on_click=_do_refine)
            ui.button("Cancel", on_click=dlg.close)
    dlg.open()


def _dlg_nl_help(session: dict) -> None:
    """In-process Q&A — keyword matching, no LLM round-trip."""
    classed    = classified_items(session)
    private    = sensitive_files(session)
    pattern    = pattern_analysis(session)
    scan       = extract_scan(session["query"])
    dup_groups = scan.get("duplicate_groups", [])

    review_items = [i for i in classed if i.get("needs_review")]
    receipts     = [i for i in classed if i.get("category") == "receipt"]
    low_conf     = [i for i in classed if i.get("confidence", 100) < 70]

    with ui.dialog() as dlg, ui.card().classes("w-[480px]"):
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.icon("help_outline", color="grey", size="lg")
            ui.label("Help me choose").classes("text-lg font-bold")
        ui.label("Ask a question about this session's results.").classes(
            "text-sm text-gray-500 mb-3"
        )
        inp     = ui.input(placeholder='e.g. "which files need review?"').classes("w-full")
        out_lbl = ui.label("").classes("text-sm text-gray-700 mt-3 whitespace-pre-wrap")

        def _answer() -> None:
            q = (inp.value or "").lower()
            if not q:
                return

            if any(kw in q for kw in ("review", "manual", "uncertain", "flag", "eye")):
                if review_items:
                    names = ", ".join(i["name"] for i in review_items)
                    out_lbl.set_text(f"{len(review_items)} file(s) need manual review:\n{names}")
                else:
                    out_lbl.set_text("No files are flagged for manual review in this session.")

            elif any(kw in q for kw in ("receipt", "invoice", "bill")):
                if receipts:
                    names = ", ".join(i["name"] for i in receipts)
                    out_lbl.set_text(f"{len(receipts)} receipt(s):\n{names}")
                else:
                    out_lbl.set_text("No receipts classified in this session.")

            elif any(kw in q for kw in ("low conf", "unsure", "uncertain", "below")):
                if low_conf:
                    lines = "\n".join(
                        f"  {i['name']} ({i.get('confidence', 0)}%)" for i in low_conf
                    )
                    out_lbl.set_text(f"{len(low_conf)} file(s) below 70 % confidence:\n{lines}")
                else:
                    out_lbl.set_text("All classified files have confidence ≥ 70 %.")

            elif any(kw in q for kw in ("private", "sensitive", "personal", "secure")):
                if private:
                    names = ", ".join(f["name"] for f in private)
                    out_lbl.set_text(
                        f"{len(private)} private file(s) — metadata only, content never read:\n{names}"
                    )
                else:
                    out_lbl.set_text("No private files flagged in this session.")

            elif any(kw in q for kw in ("duplicate", "dup", "copy", "copies")):
                if dup_groups:
                    out_lbl.set_text(
                        f"{len(dup_groups)} duplicate group(s). "
                        "Delete one copy from each to reclaim space."
                    )
                else:
                    out_lbl.set_text("No duplicates detected in this session.")

            elif any(kw in q for kw in ("how many", "count", "total", "summary")):
                out_lbl.set_text(
                    f"Session {session['sid']}:\n"
                    f"  {len(classed)} classified file(s)\n"
                    f"  {len(private)} private file(s)\n"
                    f"  {len(dup_groups)} duplicate group(s)\n"
                    f"  {len(review_items)} need manual review"
                )

            elif any(kw in q for kw in ("plan", "effort", "recommend", "medium", "best")):
                if pattern:
                    med = (pattern.get("plans") or {}).get("medium", {})
                    out_lbl.set_text(
                        f"Recommended: Medium effort ({med.get('effort', '?')})\n"
                        f"Reclaimable: {med.get('reclaimable', '?')}\n"
                        f"Risk: {med.get('risk', '?')}"
                    )
                else:
                    out_lbl.set_text("No plan data in this session.")

            else:
                out_lbl.set_text(
                    "Try asking about: manual review, receipts, low confidence, "
                    "private files, duplicates, file counts, or effort plans."
                )

        with ui.row().classes("mt-2 gap-2"):
            ui.button("Ask", icon="send", on_click=_answer)
            ui.button("Close", on_click=dlg.close)
    dlg.open()


# ── Engine re-invocation ──────────────────────────────────────────────────────

async def _run_refine(session: dict, instruction: str) -> None:
    original = session["query"]
    refined  = (
        f"REFINEMENT NOTE: {instruction}\n\n"
        f"Apply the note above to the following request:\n\n{original}"
    )

    import os, tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix="_refined.txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(refined)

    python    = str(ROOT / ".venv" / "Scripts" / "python.exe")
    organiser = str(ROOT / "run_organiser.py")
    env       = dict(os.environ)
    env_file  = ROOT / ".." / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())

    try:
        await asyncio.create_subprocess_exec(
            python, organiser,
            cwd=str(ROOT),
            env=env,
        )
        ui.notify(
            "Refinement engine running. Refresh the session picker in ~30 s.",
            type="positive",
            timeout=8000,
        )
    except Exception as exc:
        ui.notify(f"Failed to start engine: {exc}", type="negative")


# ── Page ──────────────────────────────────────────────────────────────────────

@ui.page("/")
def main_page() -> None:
    sessions = list_sessions()

    if not sessions:
        with ui.column().classes("items-center justify-center h-screen gap-4"):
            ui.icon("folder_off", size="xl", color="grey")
            ui.label("No sessions found.").classes("text-xl text-gray-400")
            ui.label("cd code && python run_organiser.py").classes(
                "text-sm font-mono text-gray-400 bg-gray-100 px-3 py-1 rounded"
            )
        return

    locked_zones: set[str] = set()
    current: dict           = {"sid": sessions[0]}

    ui.query("body").style("background-color:#f9fafb;")

    # Header
    with ui.header().classes("bg-white shadow-sm px-6 py-2 z-10"):
        with ui.row().classes("items-center gap-4 w-full"):
            ui.icon("folder_special", color="blue-8").classes("text-2xl")
            ui.label("File Organiser Assistant").classes("text-xl font-bold text-gray-800")
            ui.space()
            session_sel = ui.select(
                options=sessions, value=current["sid"], label="Session",
                on_change=lambda e: _rebuild(e.value),
            ).classes("min-w-[230px]")

            async def _new_scan() -> None:
                ui.notify("Starting new scan…", type="info")
                import os
                python = str(ROOT / ".venv" / "Scripts" / "python.exe")
                env    = dict(os.environ)
                env_f  = ROOT / ".." / ".env"
                if env_f.exists():
                    for line in env_f.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            env.setdefault(k.strip(), v.strip())
                try:
                    await asyncio.create_subprocess_exec(
                        python, str(ROOT / "run_organiser.py"),
                        cwd=str(ROOT), env=env,
                    )
                    ui.notify(
                        "Scan running. Refresh the page in ~30 s to pick the new session.",
                        type="positive", timeout=8000,
                    )
                except Exception as exc:
                    ui.notify(f"Could not start scan: {exc}", type="negative")

            ui.button("New Scan", icon="play_arrow", on_click=_new_scan).classes("ml-2")

    # Content area — rebuilt on session switch
    content = ui.column().classes("w-full max-w-5xl mx-auto px-4 py-6 gap-0")

    def _rebuild(sid: str) -> None:
        current["sid"] = sid
        content.clear()
        with content:
            session    = load_session(sid)
            node_count = len(session["nodes"])
            q_preview  = session["query"][:150].replace("\n", " ")
            if len(session["query"]) > 150:
                q_preview += "…"

            # Session banner
            with ui.row().classes("items-center gap-2 mb-4 text-xs text-gray-400"):
                ui.icon("info", size="xs")
                ui.label(f"{sid}  ·  {node_count} nodes  ·  {q_preview}")

            with ui.tabs().classes("mb-1") as tabs:
                t_dash    = ui.tab("Dashboard",     icon="dashboard")
                t_plans   = ui.tab("Compare Plans", icon="compare")
                t_filters = ui.tab("Filter Files",  icon="filter_list")
                t_hist    = ui.tab("History",        icon="history")

            with ui.tab_panels(tabs, value=t_dash).classes("w-full"):
                with ui.tab_panel(t_dash):
                    render_dashboard(session, locked_zones)
                with ui.tab_panel(t_plans):
                    render_compare_plans(session)
                with ui.tab_panel(t_filters):
                    render_filters(session)
                with ui.tab_panel(t_hist):
                    render_history(sessions)

    _rebuild(current["sid"])


# ── Entry point ───────────────────────────────────────────────────────────────

def start() -> None:
    ui.run(
        title="FileOrganiser",
        port=APP_PORT,
        reload=False,
        dark=None,   # follow OS dark-mode preference
        favicon="🗂",
        show=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    start()
