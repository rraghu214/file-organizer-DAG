"""Launch the FileOrganiser NiceGUI dashboard.

Usage (from code/):
    .venv\\Scripts\\python.exe run_ui.py
then open http://localhost:8110
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.app import start  # noqa: E402

if __name__ == "__main__":
    start()
