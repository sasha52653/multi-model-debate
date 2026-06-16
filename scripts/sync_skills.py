#!/usr/bin/env python3
"""Vendor the canonical package code into the self-contained Claude skill.

`multimodel_debate/` is the single source of truth. The Claude skill under
`skills/claude/multi-model-debate/scripts/` must be self-contained (Claude Code
copies the whole skill directory), so it carries a vendored copy of the three
modules. Run this after editing the package to keep the skill in sync:

    python scripts/sync_skills.py
"""

import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "multimodel_debate")
DST = os.path.join(ROOT, "skills", "claude", "multi-model-debate", "scripts")

MODULES = ["openrouter.py", "models.py", "debate.py"]

os.makedirs(DST, exist_ok=True)
for m in MODULES:
    shutil.copy2(os.path.join(SRC, m), os.path.join(DST, m))
    print(f"  synced {m}")
print(f"Vendored {len(MODULES)} module(s) into {DST}")
