#!/usr/bin/env bash
# Однострочный деплой kt-app в Yandex Cloud.
#
# Что делает:
#   1. Build prod Docker-образа (с baked Chroma)
#   2. Push в Container Registry (id из terraform output)
#   3. Build фронт (vite build)
#   4. Upload dist/ в Object Storage bucket
#   5. (Опционально) Trigger nadejné revision контейнера через `yc`
#
# Требует:
#   - terraform apply прошёл (есть outputs)
#   - docker запущен
#   - yc CLI установлен и авторизован (`yc init` один раз)
#   - aws CLI или s3cmd (для загрузки в bucket)
#
# Использование:
#   bash scripts/deploy.sh                # full deploy
#   bash scripts/deploy.sh --backend-only # пересобрать только бэк
#   bash scripts/deploy.sh --frontend-only

set -euo pipefail

cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

DO_BACKEND=1
DO_FRONTEND=1
IMAGE_TAG="${IMAGE_TAG:-latest}"

for arg in "$@"; do
  case "$arg" in
    --backend-only)  DO_FRONTEND=0 ;;
    --frontend-only) DO_BACKEND=0 ;;
    --tag=*)         IMAGE_TAG="${arg#--tag=}" ;;
    *)               fail "Unknown arg: $arg" ;;
  esac
done

# 0. Pre-flight
command -v terraform >/dev/null || fail "terraform не установлен"
command -v docker    >/dev/null || fail "docker не установлен"
command -v yc        >/dev/null || fail "yc CLI не установлен (https://cloud.yandex.com/docs/cli/quickstart)"

# 1. terraform outputs
pushd terraform >/dev/null
[ -f terraform.tfvars ] || fail "terraform/terraform.tfvars отсутствует. См. SETUP.md."
[ -d .terraform ]       || fail "terraform не инициализирован. Запусти: cd terraform && terraform init"

CR_ID=$(terraform output -raw container_registry_id 2>/dev/null) || fail "Нет output container_registry_id — `terraform apply` сначала"
CONTAINER_ID=$(terraform output -raw container_id)
BUCKET=$(terraform output -raw bucket_endpoint)
BUCKET_AK=$(terraform output -raw bucket_access_key)
BUCKET_SK=$(terraform output -raw bucket_secret_key)
PUBLIC_URL=$(terraform output -raw public_url)
popd >/dev/null

IMAGE_URL="cr.yandex/${CR_ID}/kt-app:${IMAGE_TAG}"

# 2. Backend: docker build + push + new revision
if [ "$DO_BACKEND" = "1" ]; then
  [ -d data/chroma ]   || fail "data/chroma/ пустой — запусти ingest локально перед deploy"
  [ -d data/exams ]    || fail "data/exams/ пустой — структура экзаменов нужна для bake"

  ok "Логинимся в Container Registry"
  yc container registry configure-docker

  ok "Сборка Docker-образа: ${IMAGE_URL}"
  docker build -f Dockerfile.prod -t "${IMAGE_URL}" .

  ok "Push в Container Registry"
  docker push "${IMAGE_URL}"

  ok "Создание новой revision контейнера"
  # Серверлесс контейнер сам подхватит новый latest на следующий запрос.
  # Но чтобы заменить ENV или image-tag — нужна явная revision:
  yc serverless container revision deploy \
    --container-id "${CONTAINER_ID}" \
    --image "${IMAGE_URL}" \
    --memory 2GB \
    --cores 1 \
    --execution-timeout 90s \
    --concurrency 4 || warn "revision deploy упал — образ запушен, но контейнер не пересоздан"
fi

# 3. Frontend: vite build + upload в bucket
if [ "$DO_FRONTEND" = "1" ]; then
  ok "Build фронта"
  (cd frontend && npm run build)

  ok "Upload в bucket ${BUCKET}"
  # Используем aws CLI с custom endpoint
  if command -v aws >/dev/null; then
    AWS_ACCESS_KEY_ID="${BUCKET_AK}" \
    AWS_SECRET_ACCESS_KEY="${BUCKET_SK}" \
      aws --endpoint-url=https://storage.yandexcloud.net \
          s3 sync frontend/dist/ "s3://${BUCKET}/" \
          --delete
  else
    warn "aws CLI не установлен — используем yc storage"
    AWS_ACCESS_KEY_ID="${BUCKET_AK}" \
    AWS_SECRET_ACCESS_KEY="${BUCKET_SK}" \
      yc storage s3 cp --recursive frontend/dist/ "s3://${BUCKET}/" || \
      fail "Загрузка не удалась. Установи aws CLI: pip install awscli"
  fi
fi

# 4. Smoke
ok "Проверка публичного URL"
sleep 2
HTTP=$(curl -sS -o /tmp/kt-healthz.json -w '%{http_code}' "${PUBLIC_URL}/healthz" || echo "000")
if [ "$HTTP" = "200" ]; then
  ok "${PUBLIC_URL}/healthz отвечает 200"
  jq -c '{status, llm_configured, exams: [.exams[].slug]}' /tmp/kt-healthz.json 2>/dev/null || cat /tmp/kt-healthz.json
else
  warn "/healthz вернул HTTP $HTTP — возможно контейнер ещё прогревается, попробуй через 30 секунд"
fi

echo
ok "Deploy завершён"
echo "Публичный URL: ${PUBLIC_URL}"
