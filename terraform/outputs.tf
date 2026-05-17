# =============================================================================
# Outputs — то, что terraform печатает после `apply`.
# Эти значения нужны для деплоя образа (push в CR) и проверки фронта.
# =============================================================================

output "container_registry_id" {
  value       = yandex_container_registry.kt.id
  description = "Идентификатор Container Registry; используется в imageUrl: cr.yandex/<id>/kt-app:<tag>"
}

output "container_id" {
  value       = yandex_serverless_container.kt.id
  description = "ID Serverless Container — для ручных вызовов через yc CLI"
}

output "public_url" {
  value       = "https://${yandex_api_gateway.kt.domain}"
  description = "Публичный URL API Gateway. Откройте его — должен показать фронт."
}

output "bucket_endpoint" {
  value       = yandex_storage_bucket.frontend.bucket
  description = "Имя bucket для фронт-статики. Загрузка: см. scripts/deploy.sh"
}

output "bucket_access_key" {
  value       = yandex_iam_service_account_static_access_key.bucket_admin_key.access_key
  sensitive   = true
  description = "Access key для S3-загрузки фронта (sensitive — печать только через `terraform output bucket_access_key`)"
}

output "bucket_secret_key" {
  value       = yandex_iam_service_account_static_access_key.bucket_admin_key.secret_key
  sensitive   = true
}

output "container_sa_id" {
  value       = yandex_iam_service_account.container_sa.id
  description = "Service account ID запущенного контейнера"
}

output "lockbox_secret_id" {
  value       = yandex_lockbox_secret.llm_api_key.id
  description = "ID секрета с LLM_API_KEY (для ротации через `yc lockbox secret add-version`)"
}
