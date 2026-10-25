#!/usr/bin/env python3
"""SessionStart hook: each time Claude Code is opened (or resumed) in the game folder, refill the meter.

A /clear or a compaction doesn't refill it; the matcher in .claude/settings.json leaves those out. Nor does a
round's referee session started by tools/rounds.py (CODERPG_NO_REFILL=1): the run refills it once, when it starts,
or the meter would refill every round. It prints nothing, because whatever a SessionStart hook prints is added to
the conversation.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

if os.environ.get("CODERPG_NO_REFILL") == "1":
    sys.exit(0)
try:
    subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), "meter", "refill"], cwd=ROOT,
                   capture_output=True, text=True, timeout=20)
except (OSError, subprocess.SubprocessError):
    pass
