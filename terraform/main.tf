# =============================================================================
# AI Knowledge Tracing — Yandex Cloud infrastructure.
#
# Создаёт минимально-достаточную инфру для публичного demo:
#   - Container Registry (хранит Docker-образ FastAPI)
#   - Serverless Container (бэк)
#   - Object Storage bucket (фронт-статика)
#   - Lockbox secret (LLM API key)
#   - Service Account для контейнера + ролей
#   - API Gateway (один публичный URL для backend + frontend)
#
# Перед `terraform apply` пользователю нужно:
#   1. Создать в Yandex Cloud Console service account "kt-deployer"
#      с ролью `admin` на folder (см. terraform/SETUP.md)
#   2. Скачать "Авторизованный ключ" в JSON, путь положить в terraform.tfvars
#   3. (Опционально) Создать billing account в console — если ещё не создан
#
# Стоимость инфры при низкой нагрузке: <200 ₽/мес (CR + bucket + LLM API за
# вычетом квоты входят в free-tier).
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = ">= 0.103"
    }
  }
}

provider "yandex" {
  service_account_key_file = var.sa_key_file
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
  zone                     = var.zone
}

# -----------------------------------------------------------------------------
# Локальные удобства
# -----------------------------------------------------------------------------

locals {
  app_name = "kt-app"
  tags = {
    project = "kn-trace-itmo"
    managed = "terraform"
  }
}

# =============================================================================
# Container Registry — хранит наш Docker image
# =============================================================================

resource "yandex_container_registry" "kt" {
  name      = "${local.app_name}-cr"
  folder_id = var.folder_id
}

# =============================================================================
# Service Account для контейнера
# =============================================================================

resource "yandex_iam_service_account" "container_sa" {
  folder_id   = var.folder_id
  name        = "${local.app_name}-runner"
  description = "Service account для Serverless Container kt-app"
}

# Роли — минимум для работы:
#  - container-registry.images.puller: чтобы container мог pull свой образ
#  - lockbox.payloadViewer: чтобы прочитать LLM_API_KEY
#  - storage.viewer: на случай интеграции с Object Storage
locals {
  container_sa_roles = [
    "container-registry.images.puller",
    "lockbox.payloadViewer",
    "storage.viewer",
  ]
}

resource "yandex_resourcemanager_folder_iam_member" "container_sa_roles" {
  for_each  = toset(local.container_sa_roles)
  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.container_sa.id}"
}

# =============================================================================
# Lockbox: LLM_API_KEY
# =============================================================================

resource "yandex_lockbox_secret" "llm_api_key" {
  folder_id   = var.folder_id
  name        = "${local.app_name}-llm-api-key"
  description = "API key для OpenAI-совместимого LLM-провайдера (OpenAI/OpenRouter/DeepSeek/YandexGPT)"
}

resource "yandex_lockbox_secret_version" "llm_api_key" {
  secret_id = yandex_lockbox_secret.llm_api_key.id

  entries {
    key        = "LLM_API_KEY"
    text_value = var.llm_api_key
  }
}

# =============================================================================
# Serverless Container — наш FastAPI бэк
# =============================================================================

resource "yandex_serverless_container" "kt" {
  name               = local.app_name
  folder_id          = var.folder_id
  description        = "AI Knowledge Tracing FastAPI backend"
  memory             = var.container_memory_mb
  execution_timeout  = "${var.container_timeout_s}s"
  cores              = var.container_cores
  concurrency        = var.container_concurrency
  service_account_id = yandex_iam_service_account.container_sa.id

  image {
    url = "cr.yandex/${yandex_container_registry.kt.id}/${local.app_name}:${var.image_tag}"

    environment = {
      LLM_BASE_URL          = var.llm_base_url
      LLM_MODEL             = var.llm_model
      LLM_MAX_TOKENS        = tostring(var.llm_max_tokens)
      LLM_MAX_INPUT_CHARS   = tostring(var.llm_max_input_chars)
      LLM_CACHE_ENABLED     = "true"
      RATE_LIMIT_PER_MIN    = tostring(var.rate_limit_per_min)
      LOG_LEVEL             = var.log_level
      SKIP_LLM              = var.skip_llm ? "true" : "false"
      # Пути overridable через переменные среды в Dockerfile.prod уже выставлены
    }

    work_dir = "/app"
  }

  # LLM API key инжектится из Lockbox как env-переменная
  secrets {
    id                   = yandex_lockbox_secret.llm_api_key.id
    version_id           = yandex_lockbox_secret_version.llm_api_key.id
    key                  = "LLM_API_KEY"
    environment_variable = "LLM_API_KEY"
  }
}

# Сделать контейнер публично-вызываемым (без auth-токена)
resource "yandex_serverless_container_iam_binding" "public_invoker" {
  container_id = yandex_serverless_container.kt.id
  role         = "serverless.containers.invoker"
  members      = ["system:allUsers"]
}

# =============================================================================
# Object Storage bucket — фронтенд статика
# =============================================================================

# Static key для подписи S3-style загрузок (из SA с storage.editor)
resource "yandex_iam_service_account" "bucket_admin" {
  folder_id   = var.folder_id
  name        = "${local.app_name}-bucket-admin"
  description = "Service account для загрузки frontend dist в bucket"
}

resource "yandex_resourcemanager_folder_iam_member" "bucket_admin_role" {
  folder_id = var.folder_id
  role      = "storage.editor"
  member    = "serviceAccount:${yandex_iam_service_account.bucket_admin.id}"
}

resource "yandex_iam_service_account_static_access_key" "bucket_admin_key" {
  service_account_id = yandex_iam_service_account.bucket_admin.id
  description        = "S3 access key for frontend uploads"
}

resource "yandex_storage_bucket" "frontend" {
  bucket     = var.bucket_name
  access_key = yandex_iam_service_account_static_access_key.bucket_admin_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.bucket_admin_key.secret_key
  folder_id  = var.folder_id

  # SPA hosting: index.html для всех путей (роутинг на клиенте)
  website {
    index_document = "index.html"
    error_document = "index.html"
  }

  # Публичный read
  acl = "public-read"
}

# =============================================================================
# API Gateway — публичный URL, объединяет container + bucket
# =============================================================================

resource "yandex_api_gateway" "kt" {
  folder_id   = var.folder_id
  name        = "${local.app_name}-gw"
  description = "Public gateway: /api/* → container, /* → bucket"

  # Спецификация в отдельном файле — там подставляем container_id и bucket
  spec = templatefile("${path.module}/api-gateway.yaml", {
    container_id       = yandex_serverless_container.kt.id
    service_account_id = yandex_iam_service_account.container_sa.id
    bucket_name        = yandex_storage_bucket.frontend.bucket
  })
}
