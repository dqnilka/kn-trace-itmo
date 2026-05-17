#!/usr/bin/env bash
# End-to-end test: Docker compose up → ingest (if needed) → POST scenario A → validate.
#
# Requires: docker compose, jq, python3, curl in PATH; SOY_TOKEN exported in shell.
#
# Usage:
#   ./scripts/e2e.sh              # full run; tears down at the end
#   ./scripts/e2e.sh --keep       # leave the stack running
#   ./scripts/e2e.sh --rebuild    # force re-ingest

set -euo pipefail

cd "$(dirname "$0")/.."

KEEP=0
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --keep) KEEP=1 ;;
    --rebuild) REBUILD=1 ;;
    -h|--help) sed -n '1,15p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

# 0. Pre-flight
[ -n "${SOY_TOKEN:-}" ] || fail "SOY_TOKEN is not set in environment. Export it first."
command -v jq >/dev/null   || fail "jq is required (brew install jq)."
command -v curl >/dev/null || fail "curl is required."
command -v docker >/dev/null || fail "docker is required."
ok "pre-flight passed (SOY_TOKEN=${#SOY_TOKEN} chars, jq+curl+docker found)"

# 1. .env
if [ ! -f .env ]; then
  cp .env.example .env
  ok "created .env from .env.example"
fi
# Make sure .env exports SOY_TOKEN from the current shell
if ! grep -q '^SOY_TOKEN=' .env; then
  echo "SOY_TOKEN=$SOY_TOKEN" >> .env
fi

# 2. CA bundle (host certs)
if [ ! -s data/ca-bundle.pem ]; then
  bash scripts/prepare_ca_bundle.sh
fi
ok "CA bundle ready ($(grep -c 'BEGIN CERTIFICATE' data/ca-bundle.pem) certs)"

# 3. Build example request
if [ ! -s examples/scenario_a_request.json ] || [ "$REBUILD" = "1" ]; then
  if [ -d .venv ]; then
    .venv/bin/python scripts/build_example_request.py
  else
    python3 scripts/build_example_request.py
  fi
fi
ok "examples/scenario_a_request.json ready"

# 4. Compose: tear down old, optionally trigger ingest
if [ "$REBUILD" = "1" ]; then
  warn "--rebuild requested: removing chroma_data volume"
  docker compose down -v >/dev/null 2>&1 || true
fi

# Ingest only if data is empty (volume not yet built or stamp missing)
NEEDS_INGEST=0
if ! docker volume inspect graph_chroma_data >/dev/null 2>&1; then
  NEEDS_INGEST=1
elif [ "$REBUILD" = "1" ]; then
  NEEDS_INGEST=1
fi

if [ "$NEEDS_INGEST" = "1" ]; then
  warn "running ingest (this can take a few minutes on first run)"
  docker compose --profile ingest run --rm ingest
  ok "ingest completed"
else
  ok "ingest already done (chroma_data volume present)"
fi

# 5. Start API
docker compose up -d api >/dev/null
ok "api container started"

# 6. Wait for /healthz
echo -n "  waiting for /healthz... "
for i in {1..60}; do
  if curl -fsS http://localhost:8000/healthz >/tmp/akt_health.json 2>/dev/null; then
    echo "ok ($i s)"
    break
  fi
  sleep 1
  [ "$i" = "60" ] && { docker compose logs --tail=80 api; fail "/healthz did not respond in 60s"; }
done
jq -e '.graph_loaded == true and .vector_store_ready == true and .llm_configured == true' /tmp/akt_health.json >/dev/null \
  || { cat /tmp/akt_health.json; fail "/healthz reported unhealthy state"; }
ok "/healthz: $(jq -c '{nodes,edges,topics}' /tmp/akt_health.json)"

# 7. POST analyze_test (scenario A)
RESP=examples/scenario_a_response.json
HTTP=$(curl -sS -o "$RESP" -w '%{http_code}' \
   -X POST http://localhost:8000/api/v1/analyze_test \
   -H 'Content-Type: application/json' \
   --data @examples/scenario_a_request.json)
[ "$HTTP" = "200" ] || { cat "$RESP"; fail "POST /analyze_test returned HTTP $HTTP"; }
ok "POST /analyze_test → 200"

# 8. jq invariants
jq -e '.status == "errors_found"' "$RESP" >/dev/null || fail "status != errors_found"
jq -e '.study_plan | length == 3' "$RESP" >/dev/null || \
  fail "study_plan must have 3 items (got $(jq '.study_plan|length' $RESP))"
jq -e '.study_plan | all(.failed_question_id and (.theory_content|length>200) and (.sources|length>0))' "$RESP" >/dev/null \
  || fail "study_plan items missing required fields"
ok "JSON invariants pass"

# 9. Referential integrity
.venv/bin/python scripts/validate_response.py "$RESP" examples/scenario_a_request.json \
  || python3 scripts/validate_response.py "$RESP" examples/scenario_a_request.json
ok "referential integrity pass"

# 10. Bonus: GET /api/v1/topics
TLIST=$(curl -fsS 'http://localhost:8000/api/v1/topics')
N=$(echo "$TLIST" | jq '.topics|length')
[ "$N" -gt 1 ] || fail "topics endpoint returned $N topics"
FIRST_NAME=$(echo "$TLIST" | jq -r '.topics[0].name')
ok "GET /api/v1/topics → $N topics (sample: '$FIRST_NAME')"

# 11. Bonus: GET /api/v1/topic_dive
TD_HTTP=$(curl -sS -o /tmp/akt_dive.json -w '%{http_code}' \
   --get 'http://localhost:8000/api/v1/topic_dive' --data-urlencode "topic_name=$FIRST_NAME")
[ "$TD_HTTP" = "200" ] || { cat /tmp/akt_dive.json; fail "topic_dive HTTP $TD_HTTP"; }
TD_Q=$(jq '.questions|length' /tmp/akt_dive.json)
ok "GET /api/v1/topic_dive?topic_name=... → 200 ($TD_Q questions)"

# 12. Perfect-score scenario
PERFECT=$(curl -fsS -X POST http://localhost:8000/api/v1/analyze_test \
   -H 'Content-Type: application/json' \
   --data @examples/scenario_a_request_perfect.json)
echo "$PERFECT" | jq -e '.status == "perfect_score"' >/dev/null \
  || { echo "$PERFECT"; fail "perfect_score scenario failed"; }
ok "POST /analyze_test (perfect) → status=perfect_score with $(echo "$PERFECT"|jq '.available_topics|length') topics"

echo
echo -e "${GREEN}=== E2E PASSED ===${NC}"
echo "Response saved at: $RESP"
echo "View it: less $RESP   |   summary: jq '.study_plan|map({failed_question_id, sources: (.sources|length), theory_len: (.theory_content|length)})' $RESP"

if [ "$KEEP" != "1" ]; then
  docker compose down >/dev/null
  ok "compose torn down"
else
  warn "--keep: containers left running (compose down to stop)"
fi
