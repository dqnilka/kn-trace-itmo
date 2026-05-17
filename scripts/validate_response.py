"""Validate Scenario A response: schema + semantic invariants + referential integrity.

Usage:
  python scripts/validate_response.py examples/scenario_a_response.json examples/scenario_a_request.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.graph.loader import load_graph  # noqa: E402

GRAPH_PATH = ROOT / "out" / "LearningChunkGraph_longrange.json"
MIN_THEORY_LEN = 200


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: validate_response.py <response.json> <request.json>", file=sys.stderr)
        sys.exit(2)
    resp_path = Path(sys.argv[1])
    req_path = Path(sys.argv[2])

    response = json.loads(resp_path.read_text(encoding="utf-8"))
    request = json.loads(req_path.read_text(encoding="utf-8"))

    expected_failed = {
        it["question_id"] for it in request["test_results"] if not it["is_correct"]
    }
    expected_count = len(expected_failed)

    if response.get("status") != "errors_found":
        fail(f"status != errors_found (got {response.get('status')!r})")

    plan = response.get("study_plan") or []
    if len(plan) != expected_count:
        fail(f"study_plan length {len(plan)} != expected {expected_count}")

    actual_failed = {it["failed_question_id"] for it in plan}
    if actual_failed != expected_failed:
        fail(f"failed_question_id mismatch: {actual_failed} vs {expected_failed}")

    # Load graph for referential integrity
    g = load_graph(GRAPH_PATH)
    valid_ids = {n.id for n in g.nodes}

    for i, item in enumerate(plan):
        loc = f"plan[{i}]({item['failed_question_id']})"
        if not item.get("question_text"):
            fail(f"{loc}: empty question_text")
        if not item.get("related_concepts"):
            fail(f"{loc}: related_concepts is empty")
        for nid in item["related_concepts"]:
            if nid not in valid_ids:
                fail(f"{loc}: related_concepts contains unknown node_id={nid!r}")
        theory = item.get("theory_content") or ""
        if len(theory) < MIN_THEORY_LEN:
            fail(f"{loc}: theory_content too short ({len(theory)} < {MIN_THEORY_LEN})")
        sources = item.get("sources") or []
        if not sources:
            fail(f"{loc}: sources is empty")
        for s in sources:
            nid = s.get("node_id")
            ntype = s.get("node_type")
            if ntype not in ("Chunk", "Concept", "Assessment", "MdChunk"):
                fail(f"{loc}: source has unknown node_type={ntype!r}")
            if ntype != "MdChunk" and nid not in valid_ids:
                fail(f"{loc}: source.node_id {nid!r} (type {ntype}) not in graph")

    print(f"OK: study_plan has {len(plan)} items.")
    print(f"OK: all {sum(len(it['related_concepts']) for it in plan)} related_concepts ids exist in graph.")
    print(f"OK: all theory_content >= {MIN_THEORY_LEN} chars.")
    print(f"OK: all sources reference real nodes (or MdChunks).")


if __name__ == "__main__":
    main()
