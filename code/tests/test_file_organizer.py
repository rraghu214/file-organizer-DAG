"""Tests for the Session 8 file-organiser additions.

Two surfaces:
  - scanner.scan(): the Tier-0/Tier-1 cheap index. Pins the three
    behaviours that must never silently regress — duplicate detection,
    folder short-circuit, and the metadata-only sensitive prefilter.
  - Graph.extend_from(): proves a planner-emitted file-organiser DAG
    (parallel classifier fan-out + a quarantine branch) wires into the
    real orchestrator graph without touching flow.py.

Run from S8/code:  python -m pytest tests/test_file_organizer.py -q
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub the gateway so importing flow/skills does not try to launch V8.
_fake_gw = types.ModuleType("gateway")
_fake_gw.LLM = object
_fake_gw.ensure_gateway = lambda: None
_fake_gw.embed = lambda *a, **k: {}
sys.modules.setdefault("gateway", _fake_gw)

import pytest
import scanner
from schemas import AgentResult, NodeSpec


# ── scanner: Tier-0 / Tier-1 ─────────────────────────────────────────────────

@pytest.fixture
def messy(tmp_path: Path) -> Path:
    (tmp_path / "Pictures" / "backup").mkdir(parents=True)
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads" / "Setup_v2_extracted" / "bin").mkdir(parents=True)

    # duplicate pair (identical content -> same hash)
    (tmp_path / "Pictures" / "a.txt").write_text("SAME")
    (tmp_path / "Pictures" / "backup" / "a_copy.txt").write_text("SAME")
    # a unique file
    (tmp_path / "Pictures" / "b.txt").write_text("UNIQUE")
    # sensitive files (flagged on name ONLY)
    (tmp_path / "Documents" / "salary_slip_apr.txt").write_text("net pay")
    (tmp_path / "Documents" / "HDFC_statement.txt").write_text("balance")
    (tmp_path / "Documents" / "PAN_card.txt").write_text("pan")
    # installer extract (should be short-circuited, not descended)
    (tmp_path / "Downloads" / "Setup_v2_extracted" / "setup.exe").write_text("x")
    (tmp_path / "Downloads" / "Setup_v2_extracted" / "bin" / "run.dll").write_text("y")
    return tmp_path


def test_duplicates_detected_by_hash(messy):
    m = scanner.scan(messy)
    groups = m["duplicate_groups"]
    assert len(groups) == 1
    assert groups[0]["count"] == 2


def test_installer_folder_short_circuited(messy):
    m = scanner.scan(messy)
    skipped = [s["path"] for s in m["skipped_folders"]]
    assert any("Setup_v2_extracted" in p for p in skipped)
    # No file from inside the installer folder should appear in the manifest.
    assert not any("Setup_v2_extracted" in f["path"] for f in m["files"])


def test_sensitive_prefilter_catches_all_three(messy):
    m = scanner.scan(messy)
    names = {Path(s["path"]).name for s in m["sensitive_candidates"]}
    assert "salary_slip_apr.txt" in names
    assert "HDFC_statement.txt" in names
    assert "PAN_card.txt" in names  # the underscore-PAN case that regressed once


def test_scan_is_cheap(messy):
    m = scanner.scan(messy)
    # Sanity: the cheap tier is fast and reads no sensitive content (it only
    # records metadata + hashes). We assert it completed and produced a
    # manifest rather than timing anything tight.
    assert m["tier0_file_count"] >= 4
    assert "scan_seconds" in m


# ── Graph wiring: planner-emitted file-organiser DAG ─────────────────────────

def test_file_organizer_dag_wires_into_real_graph():
    """A planner emitting the parallel-fan-out + quarantine shape must wire
    into the real Graph with the correct edges, with NO change to flow.py."""
    from flow import Graph
    from skills import SkillRegistry

    reg = SkillRegistry()
    g = Graph()
    planner = g.add_node("planner", inputs=["USER_QUERY"])
    g.mark(planner, "complete")

    # The shape from planner.md's file-organiser example.
    result = AgentResult(
        success=True, agent_name="planner",
        successors=[
            NodeSpec(skill="pattern_analyzer", inputs=["USER_QUERY"],
                     metadata={"label": "diag"}),
            NodeSpec(skill="classifier", inputs=["USER_QUERY"],
                     metadata={"label": "docs"}),
            NodeSpec(skill="classifier", inputs=["USER_QUERY"],
                     metadata={"label": "imgs"}),
            NodeSpec(skill="sensitive_detector", inputs=["USER_QUERY"],
                     metadata={"label": "priv"}),
            NodeSpec(skill="formatter",
                     inputs=["n:diag", "n:docs", "n:imgs", "n:priv"],
                     metadata={"label": "out"}),
        ],
    )
    added = g.extend_from(planner, result, registry=reg)
    assert len(added) == 5

    # The three independent analysis nodes + diagnosis are all ready at once
    # (only predecessor is the complete planner) — that is the parallel layer.
    ready = set(g.ready_nodes())
    skills_ready = {g.g.nodes[n]["skill"] for n in ready}
    assert "classifier" in skills_ready
    assert "sensitive_detector" in skills_ready
    assert "pattern_analyzer" in skills_ready

    # The formatter must NOT be ready — it waits on all four upstream nodes.
    formatter = [n for n in g.g.nodes if g.g.nodes[n]["skill"] == "formatter"][0]
    assert formatter not in ready
    # It should have exactly four predecessors (diag, docs, imgs, priv).
    assert len(list(g.g.predecessors(formatter))) == 4


def test_no_orchestrator_modification_needed():
    """The new skills are pure yaml + prompt; the registry loads them and
    none declares behaviour the dispatcher cannot already handle (no tools,
    no internal_successors, no critic flag)."""
    from skills import SkillRegistry
    reg = SkillRegistry()
    for name in ("classifier", "sensitive_detector", "pattern_analyzer"):
        s = reg.get(name)
        assert s.tools_allowed == []
        assert s.internal_successors == []
        assert s.critic is False
        assert s.prompt_path.exists()
