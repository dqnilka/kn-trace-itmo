"""Legacy graph loader stubs. See app/graph/__init__.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_graph(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"nodes": [], "edges": []}
    return json.loads(p.read_text(encoding="utf-8"))


def load_concept_dictionary(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"concepts": []}
    return json.loads(p.read_text(encoding="utf-8"))
