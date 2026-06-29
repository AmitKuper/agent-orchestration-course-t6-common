"""Shared constants for the match orchestrator helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

API_KEY = os.environ.get("MCP_API_KEY", "demo-key")
MAX_FORFEIT_STREAK = 3   # consecutive actor errors before technical loss
MAX_SG_RETRIES = 3       # max re-runs per sub-game on technical loss
# Sits above max_moves so the engine's own terminal condition fires first.
LOOP_CAP_MARGIN = 2
