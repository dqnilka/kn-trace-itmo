"""Generate examples/scenario_a_request.json from the real graph.

Picks 25 Assessment ids:
  - 3 "rich" (max degree, from different sections by node_offset spread)  → is_correct=False
  - 22 random Assessments                                                 → is_correct=True

The picks are deterministic (fixed seed) so the example is reproducible.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.graph.loader import load_graph  # noqa: E402

GRAPH_PATH = ROOT / "out" / "LearningChunkGraph_longrange.json"
OUT_REQ = ROOT / "examples" / "scenario_a_request.json"
OUT_PERFECT = ROOT / "examples" / "scenario_a_request_perfect.json"
SEED = 20260430
N_TOTAL = 25
N_INCORRECT = 3


def main() -> None:
    g = load_graph(GRAPH_PATH)
    # node degree (in + out)
    deg: dict[str, int] = {}
    for e in g.edges:
        deg[e.source] = deg.get(e.source, 0) + 1
        deg[e.target] = deg.get(e.target, 0) + 1
    assessments = [n for n in g.nodes if n.type == "Assessment"]
    if len(assessments) < N_TOTAL:
        raise RuntimeError(f"Not enough Assessment nodes ({len(assessments)})")

    # Sort by degree desc to find rich candidates
    rich_sorted = sorted(assessments, key=lambda n: deg.get(n.id, 0), reverse=True)
    # Pick 3 "rich" from spread-out node_offsets (so they cover different topics).
    rich_pool = rich_sorted[:30]  # top 30 by degree
    rich_pool.sort(key=lambda n: n.node_offset or 0)
    if len(rich_pool) >= 3:
        # Take ~min, median, ~max
        idx = [0, len(rich_pool) // 2, len(rich_pool) - 1]
        rich = [rich_pool[i] for i in idx]
    else:
        rich = rich_pool[:3]

    rich_ids = {n.id for n in rich}
    rest_pool = [n for n in assessments if n.id not in rich_ids]
    rng = random.Random(SEED)
    rng.shuffle(rest_pool)
    rest = rest_pool[: N_TOTAL - len(rich)]

    # Compose request: order rich among rest deterministically
    items = []
    rich_iter = iter(rich)
    rest_iter = iter(rest)
    rich_positions = {2, 13, 22}  # spread positions for is_correct=False
    for i in range(N_TOTAL):
        if i in rich_positions and (n := next(rich_iter, None)):
            items.append({"question_id": n.id, "is_correct": False})
        else:
            n = next(rest_iter, None)
            if n is None:
                # If we ran out of rest, use rich
                n = next(rich_iter, None)
                if n is None:
                    break
            items.append({"question_id": n.id, "is_correct": True})

    # Ensure all 3 rich are included
    used = {it["question_id"] for it in items}
    for n in rich:
        if n.id not in used:
            # Replace last `is_correct=True` with rich
            for j in range(len(items) - 1, -1, -1):
                if items[j]["is_correct"]:
                    items[j] = {"question_id": n.id, "is_correct": False}
                    break

    # Validate: 25 total, exactly 3 false
    assert len(items) == N_TOTAL, len(items)
    assert sum(1 for it in items if not it["is_correct"]) == N_INCORRECT, items

    request_payload = {"user_id": 12345, "test_results": items}
    OUT_REQ.parent.mkdir(parents=True, exist_ok=True)
    OUT_REQ.write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_REQ} ({len(items)} questions, {N_INCORRECT} errors)")

    # Perfect-score variant: same 25 ids, all correct
    perfect = {
        "user_id": 12345,
        "test_results": [{"question_id": it["question_id"], "is_correct": True} for it in items],
    }
    OUT_PERFECT.write_text(
        json.dumps(perfect, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_PERFECT}")

    print("--- Failed (rich) questions:")
    for it in items:
        if not it["is_correct"]:
            n = next(nn for nn in assessments if nn.id == it["question_id"])
            print(f"  {n.id}  deg={deg.get(n.id,0)}  off={n.node_offset}  text={n.text[:80]}")


if __name__ == "__main__":
    main()
