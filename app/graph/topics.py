"""Legacy topics stubs. See app/graph/__init__.py."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Topic:
    topic_id: int
    name: str
    size: int = 0


@dataclass
class TopicsBundle:
    topics: list[Topic] = field(default_factory=list)


def load_topics(path: str | Path) -> TopicsBundle:
    p = Path(path)
    if not p.exists():
        return TopicsBundle()
    data = json.loads(p.read_text(encoding="utf-8"))
    return TopicsBundle(
        topics=[
            Topic(topic_id=int(t.get("topic_id", 0)), name=str(t.get("name", "")), size=int(t.get("size", 0)))
            for t in data.get("topics", [])
        ]
    )


def save_topics(bundle: TopicsBundle, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(
            {"topics": [{"topic_id": t.topic_id, "name": t.name, "size": t.size} for t in bundle.topics]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def cluster_concepts(*_args: Any, **_kwargs: Any) -> TopicsBundle:
    """No-op clusterer. Strict pipeline supersedes this code path."""
    return TopicsBundle()
