"""The threshold grid must stay identical between the eval script and the verifier.

``scripts/verify_stage13.py`` deliberately does not import ``scripts/eval_stage13.py``
(it recomputes numbers independently), so the shared ``THRESHOLD_GRID`` can drift.
This test compares the two literals from source instead of importing either module.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_PATTERN = re.compile(r"THRESHOLD_GRID\s*(?::[^=]+)?=\s*\(([^)]*)\)")


def _grid(path: Path) -> tuple[float, ...]:
    match = _PATTERN.search(path.read_text(encoding="utf-8"))
    assert match, f"THRESHOLD_GRID not found in {path}"
    raw = match.group(1).replace("\n", " ")
    return tuple(float(item) for item in raw.split(",") if item.strip())


def test_threshold_grid_matches_eval_script() -> None:
    eval_grid = _grid(ROOT / "scripts" / "eval_stage13.py")
    verify_grid = _grid(ROOT / "scripts" / "verify_stage13.py")
    assert verify_grid == eval_grid
