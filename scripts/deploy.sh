#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REPO="${REPO:-dqnilka/kn-trace-itmo}"
REF="${REF:-master}"
PUBLIC_URL="${PUBLIC_URL:-https://d5d05aesrv8vtemcc0ga.628pfjdx.apigw.yandexcloud.net}"
CURL_BIN="${CURL_BIN:-curl}"

DO_BACKEND=true
DO_FRONTEND=true
WAIT=false
SMOKE_ONLY=false

usage() {
  cat <<'USAGE'
Usage:
  scripts/deploy.sh [--backend-only|--frontend-only] [--wait]
  scripts/deploy.sh --smoke-only

POSIX Bash helper for macOS, Linux, WSL, or Git Bash. It does not deploy local
files. It dispatches the GitHub Actions workflow on master, so production always
comes from the reviewed remote branch.

Options:
  --backend-only   Build and deploy only the backend container
  --frontend-only  Build and upload only the frontend static files
  --wait           Watch the GitHub Actions run and smoke-check prod
  --smoke-only     Only check the current production URL
  --ref=<ref>      Override GitHub ref, default: master
  --repo=<repo>    Override GitHub repo, default: dqnilka/kn-trace-itmo
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

smoke() {
  command -v "$CURL_BIN" >/dev/null 2>&1 || fail "$CURL_BIN is required for smoke checks."
  curl_flags=(--connect-timeout 8 --max-time 30 --retry 2 --retry-all-errors --retry-delay 2 -fsS)

  echo "Checking $PUBLIC_URL/healthz"
  health="$("$CURL_BIN" "${curl_flags[@]}" "$PUBLIC_URL/healthz")" || fail "healthz request failed."
  echo "$health"

  if command -v jq >/dev/null 2>&1; then
    status="$(printf '%s' "$health" | jq -r '.status')"
    llm_configured="$(printf '%s' "$health" | jq -r '.llm_configured')"
    [ "$status" = "ok" ] || fail "healthz status is $status."
    [ "$llm_configured" = "true" ] || fail "llm_configured is $llm_configured."
  else
    printf '%s' "$health" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' || fail "healthz status is not ok."
    printf '%s' "$health" | grep -Eq '"llm_configured"[[:space:]]*:[[:space:]]*true' || fail "llm_configured is not true."
  fi

  echo "Checking $PUBLIC_URL/"
  html="$("$CURL_BIN" "${curl_flags[@]}" "$PUBLIC_URL/")" || fail "frontend request failed."
  title="$(printf '%s' "$html" | grep -o '<title>[^<]*' | head -1 || true)"
  bundle="$(printf '%s' "$html" | grep -o 'index-[A-Za-z0-9_-]*\.js' | head -1 || true)"

  echo "Title: $title"
  echo "Bundle: $bundle"

  printf '%s' "$title" | grep -q 'FinUplift' || fail "frontend title is not FinUplift."
  [ -n "$bundle" ] || fail "frontend bundle was not found in HTML."

  echo "Production smoke passed."
}

for arg in "$@"; do
  case "$arg" in
    --backend-only)
      DO_BACKEND=true
      DO_FRONTEND=false
      ;;
    --frontend-only)
      DO_BACKEND=false
      DO_FRONTEND=true
      ;;
    --wait)
      WAIT=true
      ;;
    --smoke-only)
      SMOKE_ONLY=true
      ;;
    --ref=*)
      REF="${arg#--ref=}"
      ;;
    --repo=*)
      REPO="${arg#--repo=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "Unknown argument: $arg"
      ;;
  esac
done

if [ "$SMOKE_ONLY" = "true" ]; then
  smoke
  exit 0
fi

command -v gh >/dev/null 2>&1 || fail "GitHub CLI is required. Install gh or run the workflow in GitHub Actions."
gh auth status >/dev/null 2>&1 || fail "GitHub CLI is not authenticated. Run gh auth login first."

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git fetch origin "$REF" >/dev/null 2>&1 || true
  remote_sha="$(git rev-parse "origin/$REF" 2>/dev/null || true)"
  if [ -n "$remote_sha" ]; then
    echo "Remote source: origin/$REF @ ${remote_sha:0:7}"
  fi
fi

echo "Dispatching Deploy to Yandex Cloud on $REPO ref=$REF backend=$DO_BACKEND frontend=$DO_FRONTEND"
gh workflow run deploy.yml \
  --repo "$REPO" \
  --ref "$REF" \
  -f backend="$DO_BACKEND" \
  -f frontend="$DO_FRONTEND"

echo "Deploy workflow dispatched."

if [ "$WAIT" = "true" ]; then
  sleep 5
  run_id="$(gh run list --repo "$REPO" --workflow deploy.yml --branch "$REF" --limit 1 --json databaseId --jq '.[0].databaseId')"
  [ -n "$run_id" ] || fail "Could not find the dispatched workflow run."
  gh run watch "$run_id" --repo "$REPO" --exit-status
  smoke
fi
