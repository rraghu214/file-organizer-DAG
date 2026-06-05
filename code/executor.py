"""Transactional file move-executor with dry-run and undo log.

API
---
    from executor import MoveExecutor, MoveOp

    ops = [MoveOp(src=Path("a.txt"), dst=Path("docs/a.txt"), reason="...")]
    ex  = MoveExecutor(ops, sid="s8-abc123")

    report = ex.dry_run()          # read-only check
    if report.is_clean():
        undo_log = ex.apply()      # irreversible — call dry_run first
        MoveExecutor.undo(undo_log)  # reverse if needed

Safety contract
---------------
- dry_run() reads the filesystem but NEVER writes, moves, or creates dirs.
- apply() writes an undo log entry atomically (temp + os.replace) BEFORE
  each move so a crash mid-batch leaves a recoverable record on disk.
- Same-volume moves use shutil.move (os.rename path — atomic on NTFS/ext4).
  Cross-volume: shutil.copy2 → verify SHA-256 → unlink src.
- No silent overwrites: apply() raises RuntimeError on a dst collision not
  cleared by dry_run().  Callers MUST run dry_run() first.
- Undo reverses completed moves in reverse order; moves that never executed
  (crash between log-write and rename) are silently skipped.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).parent / "state"


# ── low-level helpers ─────────────────────────────────────────────────────────

def _sha256(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _atomic_write_json(path: Path, data: object) -> None:
    """Write JSON atomically: write to .tmp then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    os.replace(tmp, path)


def _can_create_dir(path: Path) -> tuple[bool, str]:
    """Walk ancestors until one exists; check it is a writable directory."""
    probe = path
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            return False, f"no existing ancestor under {path}"
        probe = parent
    if not probe.is_dir():
        return False, f"{probe} exists but is not a directory"
    if not os.access(probe, os.W_OK):
        return False, f"{probe} is not writable"
    return True, ""


def _same_device(src: Path, dst_parent: Path) -> bool:
    try:
        return os.stat(src).st_dev == os.stat(dst_parent).st_dev
    except OSError:
        return False


# ── public data types ─────────────────────────────────────────────────────────

@dataclass
class MoveOp:
    """One file move: src → dst with a human-readable reason."""
    src: Path
    dst: Path
    reason: str = ""

    def __post_init__(self) -> None:
        self.src = Path(self.src)
        self.dst = Path(self.dst)


@dataclass
class Conflict:
    """A problem detected during dry_run that blocks a MoveOp."""
    src: str
    dst: str
    kind: str    # "src_missing" | "dst_collision" | "dst_parent_unwritable"
    detail: str


@dataclass
class DryRunReport:
    """Result of MoveExecutor.dry_run()."""
    ops: list[MoveOp]
    conflicts: list[Conflict]
    reclaimable_bytes: int

    def is_clean(self) -> bool:
        """True when there are no conflicts — safe to call apply()."""
        return len(self.conflicts) == 0


@dataclass
class MoveRecord:
    """One completed (or intended) file move, written to the undo log."""
    from_path: str
    to_path: str
    timestamp: str


@dataclass
class UndoLog:
    """Ordered list of moves that can be reversed by MoveExecutor.undo()."""
    sid: str
    moves: list[MoveRecord] = field(default_factory=list)
    log_path: Path = field(default_factory=Path)

    def to_dict(self) -> dict:
        return {
            "sid": self.sid,
            "moves": [
                {"from": r.from_path, "to": r.to_path, "timestamp": r.timestamp}
                for r in self.moves
            ],
        }

    @classmethod
    def from_path(cls, path: Path) -> "UndoLog":
        data = json.loads(path.read_text(encoding="utf-8"))
        log = cls(sid=data.get("sid", ""), log_path=path)
        for m in data.get("moves", []):
            log.moves.append(MoveRecord(
                from_path=m["from"],
                to_path=m["to"],
                timestamp=m.get("timestamp", ""),
            ))
        return log


# ── executor ──────────────────────────────────────────────────────────────────

class MoveExecutor:
    """Execute (or preview, or undo) a batch of file-move operations."""

    def __init__(self, plan: list[MoveOp], sid: str = "") -> None:
        self.plan: list[MoveOp] = [
            op if isinstance(op, MoveOp) else MoveOp(**op)
            for op in plan
        ]
        self.sid = sid or datetime.now(timezone.utc).strftime("manual_%Y%m%d_%H%M%S")
        self._log_path = STATE_DIR / f"undo_{self.sid}.json"

    # ── dry_run ───────────────────────────────────────────────────────────────

    def dry_run(self) -> DryRunReport:
        """Validate all ops.  Reads the filesystem; never writes or moves."""
        conflicts: list[Conflict] = []
        reclaimable: int = 0

        for op in self.plan:
            # 1. src must exist
            if not op.src.exists():
                conflicts.append(Conflict(
                    src=str(op.src), dst=str(op.dst),
                    kind="src_missing",
                    detail=f"{op.src} does not exist",
                ))
                continue

            # 2. dst parent must be creatable
            ok, msg = _can_create_dir(op.dst.parent)
            if not ok:
                conflicts.append(Conflict(
                    src=str(op.src), dst=str(op.dst),
                    kind="dst_parent_unwritable",
                    detail=msg,
                ))
                continue

            # 3. dst collision?
            if op.dst.exists():
                try:
                    src_hash = _sha256(op.src)
                    dst_hash = _sha256(op.dst)
                    if src_hash == dst_hash:
                        # Identical duplicate already at destination — reclaimable
                        reclaimable += op.src.stat().st_size
                    else:
                        conflicts.append(Conflict(
                            src=str(op.src), dst=str(op.dst),
                            kind="dst_collision",
                            detail=f"{op.dst} already exists with different content",
                        ))
                except OSError as exc:
                    conflicts.append(Conflict(
                        src=str(op.src), dst=str(op.dst),
                        kind="dst_collision",
                        detail=f"cannot compare hashes: {exc}",
                    ))

        return DryRunReport(
            ops=self.plan,
            conflicts=conflicts,
            reclaimable_bytes=reclaimable,
        )

    # ── apply ─────────────────────────────────────────────────────────────────

    def apply(self) -> UndoLog:
        """Execute all ops.

        For each op:
          1. Write undo log entry atomically BEFORE the move (crash-safe).
          2. Create dst parent directory.
          3. Move: same-volume → shutil.move (atomic rename).
                   cross-volume → copy2 + verify SHA-256 + unlink src.

        Raises RuntimeError if src is missing or dst would silently overwrite
        content not pre-cleared by dry_run().
        """
        undo = UndoLog(sid=self.sid, log_path=self._log_path)

        for op in self.plan:
            if not op.src.exists():
                raise RuntimeError(f"apply: src missing: {op.src}")

            if op.dst.exists():
                try:
                    if _sha256(op.src) == _sha256(op.dst):
                        # Identical duplicate already at dst — skip, nothing to undo
                        continue
                except OSError:
                    pass
                raise RuntimeError(
                    f"apply: dst collision at {op.dst}; run dry_run() first "
                    "and resolve conflicts before calling apply()"
                )

            op.dst.parent.mkdir(parents=True, exist_ok=True)

            ts = datetime.now(timezone.utc).isoformat()
            record = MoveRecord(
                from_path=str(op.src),
                to_path=str(op.dst),
                timestamp=ts,
            )

            # --- Write undo log BEFORE the move ---
            # A crash after this write but before the rename leaves the undo
            # log with this entry.  undo() checks dst.exists() before reversing
            # so an unexecuted move is harmlessly skipped.
            undo.moves.append(record)
            _atomic_write_json(self._log_path, undo.to_dict())

            # --- Execute the move ---
            if _same_device(op.src, op.dst.parent):
                # os.rename path via shutil.move — atomic on NTFS / ext4
                shutil.move(str(op.src), str(op.dst))
            else:
                # Cross-volume: copy → verify → delete
                shutil.copy2(str(op.src), str(op.dst))
                dst_hash = _sha256(op.dst)
                src_hash = _sha256(op.src)
                if dst_hash != src_hash:
                    op.dst.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"apply: SHA-256 mismatch after cross-volume copy of "
                        f"{op.src} — dst deleted, src preserved"
                    )
                op.src.unlink()

        return undo

    # ── undo ──────────────────────────────────────────────────────────────────

    @staticmethod
    def undo(log: UndoLog) -> None:
        """Reverse all moves in log, in reverse order.

        Moves that never executed (dst absent) are silently skipped — this
        happens when a crash occurred between the log-write and the rename.
        """
        for record in reversed(log.moves):
            dst = Path(record.to_path)
            src = Path(record.from_path)
            if not dst.exists():
                continue
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))

    @staticmethod
    def load_undo_log(path: Path) -> UndoLog:
        """Read a previously written undo log from disk."""
        return UndoLog.from_path(path)

    @staticmethod
    def list_undo_logs() -> list[Path]:
        """Return all undo log files under state/, newest first."""
        if not STATE_DIR.exists():
            return []
        logs = sorted(STATE_DIR.glob("undo_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return logs
