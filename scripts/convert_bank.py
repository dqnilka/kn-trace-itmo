"""Convert FSFR knowledge XLSX into a JSON question bank consumed by the frontend.

Usage:
    python scripts/convert_bank.py [source.xlsx] [target.json]

Defaults:
    source: data/sources/fsfr_bazoviy_knowledge.xlsx
    target: frontend/public/exam-basic.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import openpyxl  # type: ignore
except ImportError:
    sys.stderr.write("openpyxl is required: pip install openpyxl\n")
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "data" / "sources" / "fsfr_bazoviy_knowledge.xlsx"
DEFAULT_DST = ROOT / "data" / "exams" / "fsfr-basic" / "bank.json"


def _norm_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_bool(v) -> bool:
    return str(v).strip() in {"1", "True", "true"}


def convert(src: Path, dst: Path) -> dict:
    wb = openpyxl.load_workbook(src, data_only=True, read_only=True)

    def sheet(name: str) -> list[dict]:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        header = rows[0]
        return [dict(zip(header, r)) for r in rows[1:] if any(c is not None for c in r)]

    chapters_raw = sheet("chapters")
    themes_raw = sheet("themes")
    tasks_raw = sheet("tasks")
    options_raw = sheet("task_options")

    chapters = [
        {
            "id": _norm_int(c["pk_chapter_id"]),
            "num": _norm_int(c["chapter_num"]),
            "name": (c["chapter_name"] or "").strip(),
        }
        for c in chapters_raw
    ]

    themes = [
        {
            "id": _norm_int(t["pk_theme_id"]),
            "chapter_id": _norm_int(t["fk_chapter_id"]),
            "code": (t["theme_code"] or "").strip(),
            "name": (t["theme_name"] or "").strip(),
        }
        for t in themes_raw
    ]

    import re

    def _clean_option_text(label: str, raw: str) -> str:
        text = (raw or "").strip()
        # Source data ships option_text with the label baked in: "1. ..." or "I. ...".
        # Strip it once so renderers can format the label separately.
        pattern = rf"^{re.escape(label)}[\.\)]\s*"
        return re.sub(pattern, "", text, count=1)

    options_by_task: dict[int, list[dict]] = defaultdict(list)
    seen: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for o in options_raw:
        fk = _norm_int(o["fk_task_id"])
        if fk is None:
            continue
        label = str(o["option_label"]).strip()
        text = _clean_option_text(label, o["option_text"] or "")
        key = (label, text)
        if key in seen[fk]:
            continue
        seen[fk].add(key)
        options_by_task[fk].append(
            {
                "label": label,
                "text": text,
                "is_correct": _norm_bool(o["is_correct"]),
            }
        )
    for opts in options_by_task.values():
        opts.sort(key=lambda x: (len(x["label"]), x["label"]))

    tasks = []
    for t in tasks_raw:
        tid = _norm_int(t["pk_task_id"])
        opts = options_by_task.get(tid, [])
        if not opts:
            continue
        tasks.append(
            {
                "id": tid,
                "theme_code": (t["theme"] or "").strip(),
                "task_number": (t["task_number"] or "").strip(),
                "task_text": (t["task_text"] or "").strip(),
                "answer_type": (t["answer_type"] or "").strip(),
                "difficulty": _norm_int(t["difficulty"]),
                "solution_text": (t["solution_text"] or "").strip(),
                "options": opts,
            }
        )

    bank = {
        "_meta": {
            "exam": "Базовый экзамен ФСФР",
            "source_file": src.name,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats": {
                "chapters": len(chapters),
                "themes": len(themes),
                "tasks": len(tasks),
                "options": sum(len(t["options"]) for t in tasks),
            },
        },
        "chapters": chapters,
        "themes": themes,
        "tasks": tasks,
    }

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    return bank["_meta"]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DST
    meta = convert(src, dst)
    print(f"Wrote {dst}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
