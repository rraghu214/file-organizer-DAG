"""Reusable NiceGUI micro-components."""
from __future__ import annotations

from nicegui import ui

CATEGORY_COLOR: dict[str, str] = {
    "receipt":   "orange",
    "document":  "blue",
    "photo":     "purple",
    "code":      "teal",
    "private":   "red",
    "other":     "grey",
}


def stat_card(label: str, value: str, icon: str, color: str = "blue") -> None:
    with ui.card().classes("p-4 min-w-[138px] shadow-sm"):
        with ui.row().classes("items-center gap-3"):
            ui.icon(icon, color=color).classes("text-3xl")
            with ui.column().classes("gap-0 leading-tight"):
                ui.label(value).classes("text-2xl font-bold leading-none")
                ui.label(label).classes("text-xs text-gray-500 mt-0.5")


def conf_bar(confidence: int) -> None:
    """Horizontal progress bar + percentage label."""
    color = "positive" if confidence >= 80 else "warning" if confidence >= 60 else "negative"
    with ui.row().classes("items-center gap-2 w-full"):
        ui.linear_progress(value=confidence / 100, color=color, size="6px").classes("flex-1")
        ui.label(f"{confidence}%").classes("text-xs text-gray-400 w-9 text-right")


def file_row(item: dict) -> None:
    """One file line inside a destination group expansion."""
    cat    = item.get("category", "other")
    conf   = item.get("confidence", 0)
    review = item.get("needs_review", False)

    with ui.row().classes("items-start gap-2 py-1.5 border-b border-gray-100 w-full"):
        ui.icon(
            "visibility" if review else "check",
            color="orange" if review else "green",
            size="xs",
        ).classes("mt-0.5 shrink-0")
        with ui.column().classes("flex-1 gap-0"):
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.label(item.get("name", "?")).classes("font-mono text-sm")
                ui.badge(cat, color=CATEGORY_COLOR.get(cat, "grey")).classes("text-xs")
                if review:
                    ui.badge("needs your eyes", color="orange").classes("text-xs")
            ui.label(item.get("reason", "")).classes("text-xs text-gray-500")
        ui.label(f"{conf}%").classes("text-xs text-gray-400 self-center w-9 text-right")


def section_header(text: str, icon: str = "", color: str = "gray-600") -> None:
    with ui.row().classes("items-center gap-2 mb-2"):
        if icon:
            ui.icon(icon, color=color.split("-")[0] if "-" in color else color)
        ui.label(text).classes(f"text-sm font-semibold text-{color}")
