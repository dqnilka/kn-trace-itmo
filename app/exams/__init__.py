"""Multi-exam registry and per-exam bank loader.

Each exam is a self-contained directory under ``EXAMS_DIR`` (default
``data/exams``) with at minimum an ``exam.json`` manifest and a ``bank.json``
produced by ``scripts/convert_bank.py``. The pipeline (``pipeline/strict``)
may add more artifacts later (``graph.json``, ``concepts.json``,
``theme_sections.json``).
"""

from app.exams.registry import (  # re-export
    Exam,
    ExamRegistry,
    UnknownExamError,
    load_bank,
)

__all__ = ["Exam", "ExamRegistry", "UnknownExamError", "load_bank"]
