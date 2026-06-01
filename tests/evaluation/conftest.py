"""Shared fixtures for evaluation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.exams.bkt import MasteryStore
from evaluation.metrics.bkt import load_events

FIXTURES_DIR = Path(__file__).parent.parent.parent / "evaluation" / "fixtures" / "test_exam"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def events(fixtures_dir: Path) -> list[dict]:
    return load_events(fixtures_dir / "events.jsonl")


@pytest.fixture
def bank_data(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "bank.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def graph_data(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "graph.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def explanation_texts(fixtures_dir: Path) -> list[str]:
    from evaluation.metrics.explanation import load_explanations_from_dir
    return load_explanations_from_dir(fixtures_dir / "explanations")


@pytest.fixture
def summary_texts(fixtures_dir: Path) -> list[str]:
    from evaluation.metrics.summary import load_summaries_from_dir
    return load_summaries_from_dir(fixtures_dir / "summaries")


@pytest.fixture
def theme_codes(graph_data: dict) -> list[str]:
    return [
        n.get("code", "") for n in graph_data.get("nodes", [])
        if n.get("type") == "Theme"
    ]


@pytest.fixture
def concept_ids(graph_data: dict) -> list[str]:
    return [
        n.get("id", "") for n in graph_data.get("nodes", [])
        if n.get("type") == "Concept"
    ]


@pytest.fixture
def synthetic_store() -> MasteryStore:
    store = MasteryStore(user_id=1, exam_slug="test-exam")
    concepts = ["co:finansovyj-rynok", "co:czennaya-bumaga", "co:obligaciya", "co:akciya"]
    base_time = 1700000000.0
    for i, cid in enumerate(concepts):
        store.by_concept[cid] = 0.3 + i * 0.15
        store.last_seen[cid] = base_time - 3600 * (i + 1)
        store.stability[cid] = 86400.0 * (i + 1)
    store.events = 20
    return store
