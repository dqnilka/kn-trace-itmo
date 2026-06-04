# =============================================================================
# Переменные terraform. Подставляются из terraform.tfvars или env (TF_VAR_*).
# =============================================================================

# -----------------------------------------------------------------------------
# Yandex Cloud — обязательно
# -----------------------------------------------------------------------------

variable "cloud_id" {
  type        = string
  description = "Yandex Cloud ID (видно вверху Console: 'Облако > b1g...')"
}

variable "folder_id" {
  type        = string
  description = "Folder ID (видно в Console: 'Каталог > b1g...')"
}

variable "zone" {
  type        = string
  default     = "ru-central1-a"
  description = "Зона для compute-ресурсов"
}

variable "sa_key_file" {
  type        = string
  description = "Путь к JSON-файлу ключа service-account 'kt-deployer' (см. SETUP.md шаг 2)"
}

# -----------------------------------------------------------------------------
# LLM провайдер
# -----------------------------------------------------------------------------

variable "llm_api_key" {
  type        = string
  sensitive   = true
  description = "API ключ публичного LLM-провайдера (OpenAI / OpenRouter / DeepSeek / YandexGPT)"
}

variable "llm_base_url" {
  type        = string
  default     = "https://api.openai.com/v1"
  description = "OpenAI-совместимый endpoint провайдера"
}

variable "llm_model" {
  type        = string
  default     = "gpt-4o-mini"
  description = "Имя модели у провайдера"
}

variable "llm_auth_scheme" {
  type        = string
  default     = ""
  description = "Схема авторизации LLM-эндпоинта: 'bearer' (OpenAI/IAM-токен) или 'api-key' (YandexGPT со статическим ключом сервисного аккаунта). Пусто = автоопределение."
}

variable "llm_max_tokens" {
  type        = number
  default     = 1200
  description = "Hard cap на длину ответа LLM"
}

variable "llm_max_input_chars" {
  type        = number
  default     = 14000
  description = "Hard cap на длину prompt"
}

variable "skip_llm" {
  type        = bool
  default     = false
  description = "Если true — бэк не вызывает LLM, возвращает extractive fallback. Для проверки инфры без трат на токены."
}

# -----------------------------------------------------------------------------
# Container sizing
# -----------------------------------------------------------------------------

variable "container_memory_mb" {
  type        = number
  default     = 2048
  description = "RAM (MB). Минимум 2GB чтобы влезли E5 + cross-encoder + chroma."
}

variable "container_cores" {
  type        = number
  default     = 1
  description = "vCPU"
}

variable "container_timeout_s" {
  type        = number
  default     = 90
  description = "Execution timeout per request"
}

variable "container_concurrency" {
  type        = number
  default     = 4
  description = "Concurrent requests per instance"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Тэг Docker-образа в Container Registry"
}

# -----------------------------------------------------------------------------
# Application config
# -----------------------------------------------------------------------------

variable "rate_limit_per_min" {
  type        = number
  default     = 30
  description = "Rate-limit (req/min/IP). 0 — выключено."
}

variable "log_level" {
  type        = string
  default     = "INFO"
}

variable "bucket_name" {
  type        = string
  description = "Имя S3-bucket для фронта (должно быть глобально уникальным; например 'kt-frontend-<your-tag>')"
}
