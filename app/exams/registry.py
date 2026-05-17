"""Exam registry: scans ``EXAMS_DIR`` for exam manifests and exposes them.

A valid exam directory contains::

    <slug>/
      exam.json     # manifest (required)
      bank.json     # converted question bank (required for trainer to function)

Manifest schema (loose, additive over time)::

    {
      "slug": "fsfr-basic",
      "title": "Базовый экзамен ФСФР",
      "subtitle": "...",            # optional
      "version": "1.0.0",
      "published": true,
      "bank_path": "bank.json",     # relative to exam dir
      "theory_path": "../../theory_economics.md",  # optional, used by RAG
      "rag": {
        "collections": ["md_chunks", "graph_chunks"],
        "top_k": 6
      }
    }

The registry is intentionally read-only at runtime. The admin API (later)
will write manifests and trigger pipeline runs; this module only loads them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.core.logging import get_logger

logger = get_logger(__name__)


class UnknownExamError(KeyError):
    """Raised when a slug doesn't match any registered exam."""


@dataclass(frozen=True)
class Exam:
    slug: str
    title: str
    subtitle: str
    version: str
    published: bool
    root: Path  # exam dir on disk
    bank_path: Path  # absolute
    theory_path: Path | None  # absolute or None
    rag_collections: tuple[str, ...]
    rag_top_k: int
    # `dict` is unhashable; exclude from the dataclass hash/equality so Exam
    # stays usable as a cache key.
    raw_manifest: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def has_theory(self) -> bool:
        return self.theory_path is not None and self.theory_path.exists()


def _resolve(base: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    p = Path(rel)
    return p if p.is_absolute() else (base / p).resolve()


def load_exam(manifest_path: Path) -> Exam:
    """Parse a single ``exam.json`` into an :class:`Exam`.

    Tolerant of missing bank/theory files: admin needs to see ``draft`` exams
    that haven't had artifacts uploaded yet. Trainer endpoints should check
    ``exam.bank_path.exists()`` before using bank-dependent features.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent.resolve()

    slug = str(data["slug"])
    bank_rel = data.get("bank_path", "bank.json")
    bank_abs = _resolve(root, bank_rel) or (root / "bank.json")

    theory_abs = _resolve(root, data.get("theory_path"))
    rag = data.get("rag") or {}
    collections = tuple(rag.get("collections") or ("md_chunks", "graph_chunks"))
    top_k = int(rag.get("top_k") or 6)

    return Exam(
        slug=slug,
        title=str(data.get("title", slug)),
        subtitle=str(data.get("subtitle", "")),
        version=str(data.get("version", "0.0.0")),
        published=bool(data.get("published", True)),
        root=root,
        bank_path=bank_abs,
        theory_path=theory_abs,
        rag_collections=collections,
        rag_top_k=top_k,
        raw_manifest=data,
    )


class ExamRegistry:
    """In-memory registry of all exams discovered under ``exams_dir``.

    Discovery is shallow: each top-level directory containing ``exam.json`` is
    treated as an exam. Hidden directories (starting with ``.``) are skipped.
    """

    def __init__(self, exams_dir: Path) -> None:
        self.exams_dir = exams_dir
        self._by_slug: dict[str, Exam] = {}
        self.reload()

    def reload(self) -> None:
        self._by_slug.clear()
        if not self.exams_dir.exists():
            logger.warning("Exams dir does not exist: %s", self.exams_dir)
            return
        for sub in sorted(self.exams_dir.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            manifest = sub / "exam.json"
            if not manifest.exists():
                continue
            try:
                exam = load_exam(manifest)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to load exam at %s: %s", manifest, e)
                continue
            self._by_slug[exam.slug] = exam
            logger.info(
                "Loaded exam %s (title=%r, bank=%s, theory=%s)",
                exam.slug, exam.title, exam.bank_path.name,
                exam.theory_path.name if exam.theory_path else "—",
            )

    def all(self) -> Iterable[Exam]:
        return self._by_slug.values()

    def published(self) -> list[Exam]:
        return [e for e in self._by_slug.values() if e.published]

    def get(self, slug: str) -> Exam:
        if slug not in self._by_slug:
            raise UnknownExamError(slug)
        return self._by_slug[slug]


@lru_cache(maxsize=8)
def load_bank(exam: Exam) -> dict:
    """Read and cache the bank JSON for an exam.

    Cache key is ``Exam`` (frozen dataclass) — multiple calls return the same
    in-memory dict. Reload exam via :meth:`ExamRegistry.reload` to bust.
    """
    return json.loads(exam.bank_path.read_text(encoding="utf-8"))
