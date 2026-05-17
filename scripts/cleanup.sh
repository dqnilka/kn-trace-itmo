#!/usr/bin/env bash
# Удаление junk-файлов из репо.
#
# Что удаляет:
#   - Python bytecode кэш (__pycache__, *.pyc)
#   - .pytest_cache, .ruff_cache, .mypy_cache (если есть)
#   - macOS .DS_Store
#   - frontend/vite.log
#   - tests/_artifacts/*.log
#   - examples/scenario_a_response.{before_fix,fix1,fix2,rerank_blend07}.json (архивы)
#   - data/exams/*/backups/ (старые ревизии графа от strict pipeline)
#   - Пустые placeholder-файлы: t.md
#   - Устаревший дубликат: "README copy.md"
#
# Что НЕ трогает:
#   - frontend/node_modules (нужны для dev)
#   - data/chroma, data/exams/*/bank.json, .../graph.json, .../theory.md (нужны runtime)
#   - out/ (k2-18 artifacts — нужны для ingest)
#   - vendor/k2-18 (vendored библиотека)
#   - staging/ (slice'ы — нужны при re-ingest)
#   - .env, terraform.tfvars, kt-deployer-key.json (секреты — не удаляются,
#     но добавлены в .gitignore чтобы случайно не закоммитить)
#
# Использование:
#   bash scripts/cleanup.sh         # удалить + показать что удалено
#   bash scripts/cleanup.sh --dry-run   # только показать, ничего не удалять

set -euo pipefail
cd "$(dirname "$0")/.."

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; fi

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

remove() {
  local target="$1"
  if [ ! -e "$target" ]; then
    return 0
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo -e "  ${YELLOW}DRY${NC} would remove: $target"
  else
    # Кавычки вокруг $target обязательны: иначе имена с пробелами вроде
    # "README copy.md" расщепляются на два аргумента и не удаляются.
    rm -rf -- "$target"
    echo -e "  ${GREEN}✓${NC} removed: $target"
  fi
}

echo "=== Python bytecode ==="
while IFS= read -r d; do remove "$d"; done < <(find . -type d -name "__pycache__" -not -path "./frontend/node_modules/*" 2>/dev/null)
while IFS= read -r f; do remove "$f"; done < <(find . -type f -name "*.pyc" -not -path "./frontend/node_modules/*" 2>/dev/null)

echo "=== Tool caches ==="
remove ".pytest_cache"
remove ".ruff_cache"
remove ".mypy_cache"

echo "=== OS metadata ==="
while IFS= read -r f; do remove "$f"; done < <(find . -name ".DS_Store" 2>/dev/null)

echo "=== Dev logs ==="
remove "frontend/vite.log"
remove "tests/_artifacts"

echo "=== Empty / duplicate placeholders ==="
remove "t.md"
remove "README copy.md"

echo "=== Archived response fixtures ==="
remove "examples/scenario_a_response.before_fix.json"
remove "examples/scenario_a_response.fix1.json"
remove "examples/scenario_a_response.fix2.json"
remove "examples/scenario_a_response.rerank_blend07.json"

echo "=== Strict-pipeline graph backups ==="
while IFS= read -r d; do remove "$d"; done < <(find data/exams -type d -name "backups" 2>/dev/null)

echo ""
if [ "$DRY_RUN" = "1" ]; then
  echo -e "${YELLOW}DRY RUN — ничего не удалено. Запусти без --dry-run чтобы применить.${NC}"
else
  echo -e "${GREEN}✓ Cleanup done.${NC}"
  echo "Размер репо после чистки:"
  du -sh . 2>/dev/null | head -1 || true
fi
