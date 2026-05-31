"""Phase-0 launcher: scan demo_messy_drive and feed result into the DAG."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import scan as scan_folder
from flow import Executor

TARGET = ROOT.parent / "demo_messy_drive"

QUERY_TEMPLATE = """\
Analyse and organise this folder. Diagnose how well it is currently organised, \
classify each non-sensitive file batch (documents, photos, receipts) in parallel, \
flag any private/financial files from metadata only (never read their content), \
compute duplicate files and reclaimable space, and produce a phase-1 report \
with minimal/medium/best effort plans.

SCAN_RESULT:
{scan_json}
"""


async def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else TARGET
    print(f"[run_organiser] scanning {folder} ...")
    result = scan_folder(str(folder))
    scan_json = json.dumps(result, indent=2)
    query = QUERY_TEMPLATE.format(scan_json=scan_json)
    print(f"[run_organiser] {result['tier0_file_count']} files, "
          f"{len(result['sensitive_candidates'])} sensitive, "
          f"{len(result['duplicate_groups'])} dup groups — handing to DAG\n")
    await Executor().run(query)


if __name__ == "__main__":
    asyncio.run(main())
