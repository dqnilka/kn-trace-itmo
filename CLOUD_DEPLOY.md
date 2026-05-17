# Public deploy — Yandex Cloud + публичный LLM-провайдер

Этот документ — пошаговый рецепт «как сделать так, чтобы по ссылке открывалось у всех». Сервис в любой точке мира; LLM-провайдер OpenAI-совместимый (любой); инфра — Yandex Cloud (квота 16к ₽/мес покрывает с большим запасом).

## Архитектура

```
┌──────────┐    https        ┌─────────────────────┐
│ Browser  │ ──────────────► │ YC API Gateway      │
└──────────┘                 │  /api/* → Container │
                             │  /*     → Bucket    │
                             └──────────┬──────────┘
                                        │
                ┌───────────────────────┴───────────────────────┐
                │                                               │
                ▼                                               ▼
       ┌────────────────────┐                       ┌────────────────────┐
       │ YC Serverless      │                       │ YC Object Storage  │
       │ Container          │                       │ (frontend/dist)    │
       │  • FastAPI         │                       └────────────────────┘
       │  • ChromaDB (RO)   │
       │  • Lockbox secrets │
       └─────────┬──────────┘
                 │ outbound https
                 ▼
       ┌────────────────────┐
       │ LLM provider       │   (OpenAI / OpenRouter / DeepSeek / YandexGPT)
       │  /v1/chat/...      │
       └────────────────────┘
```

## Стоимость (оценка)

| Ресурс | Цена | Расход / мес |
|---|---|---|
| Serverless Container (1 vCPU, 1 GiB, 100 ms / req) | ≈0.5 ₽ / 1k req | 1-2 тыс. запросов / месяц от тестировщиков → 1-2 ₽ |
| Object Storage (frontend, 5 MB) | бесплатно (< 1 GB) | 0 ₽ |
| API Gateway | бесплатно (< 100k req/мес) | 0 ₽ |
| Lockbox (1 секрет) | бесплатно (< 1k операций) | 0 ₽ |
| **Итого инфра** | | **≈ 100 ₽/мес** в реалистичной нагрузке |
| **LLM** | зависит от провайдера + кэша | см. ниже |

После прогрева кэша 90%+ запросов отвечают без обращения к LLM. Реальный расход на LLM при демо для группы 20 студентов с 50 вопросов каждый — менее $5.

## Шаг 1. Подготовка LLM-провайдера

1. Зарегистрироваться у выбранного провайдера и получить API-ключ. Рекомендации в порядке оптимальности по цене/качеству для русскоязычных задач:
   - **DeepSeek** — `deepseek-chat` ≈ $0.27 / 1M output tokens
   - **OpenRouter + claude-3.5-haiku** — ≈ $4 / 1M output
   - **OpenAI gpt-4o-mini** — ≈ $0.6 / 1M output
   - **YandexGPT-Lite** — в рамках квоты 16к ₽/мес (отдельная квота от инфры)

2. Положить ключ в Lockbox:

```bash
yc lockbox secret create \
  --name kt-llm \
  --description "LLM API key for kn-trace" \
  --payload '[{"key": "LLM_API_KEY", "text_value": "sk-..."}]'
```

3. Запомнить `LOCKBOX_SECRET_ID` из вывода — пригодится в шаге 3.

## Шаг 2. Сборка Docker-образа с предзаполненной Chroma

Чтобы Serverless Container не делал ingest на каждом старте (минут 5-7), запекаем готовую Chroma и модели в образ.

```bash
# Локально: подготовить chroma и hf-cache
docker compose --profile ingest run --rm ingest

# Собрать продакшен-образ с включённой chroma
docker build -t cr.yandex/<registry-id>/kt-app:latest \
  --build-arg BAKE_CHROMA=true .

# Аутентификация в Container Registry YC
yc container registry configure-docker

# Push
docker push cr.yandex/<registry-id>/kt-app:latest
```

В `Dockerfile` (на момент написания) baking ещё не реализован — нужно добавить `COPY data/chroma /app/data/chroma` под условие `BAKE_CHROMA`. (Это часть TODO следующего шага.)

## Шаг 3. Deploy Serverless Container

```bash
yc serverless container create --name kt-app

yc serverless container revisions deploy \
  --container-name kt-app \
  --image cr.yandex/<registry-id>/kt-app:latest \
  --cores 1 \
  --memory 2GB \
  --execution-timeout 90s \
  --concurrency 4 \
  --service-account-id <sa-id> \
  --secret environment-variable=LLM_API_KEY,id=<LOCKBOX_SECRET_ID>,version-id=<ver>,key=LLM_API_KEY \
  --environment LLM_BASE_URL=https://api.deepseek.com/v1,LLM_MODEL=deepseek-chat,LLM_CACHE_ENABLED=true,RATE_LIMIT_PER_MIN=30,EXAMS_DIR=/app/exams
```

После деплоя получаем https-URL вида `https://bba<id>.containers.yandexcloud.net`.

## Шаг 4. Frontend в Object Storage

```bash
# Локально
cd frontend && npm run build
# Загрузка
yc storage bucket create --name kt-frontend
yc storage bucket update --name kt-frontend \
  --website-settings index-page-prefix=index.html,error-page=index.html
aws s3 sync ./dist s3://kt-frontend/ \
  --endpoint-url=https://storage.yandexcloud.net
```

## Шаг 5. API Gateway

```yaml
# api-gw.yaml
openapi: 3.0.0
info: { title: kt-app, version: "1" }
paths:
  /api/{rest+}:
    x-yc-apigateway-any-method:
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: <container-id>
        service_account_id: <sa-id>
  /healthz:
    get:
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: <container-id>
        service_account_id: <sa-id>
  /{rest+}:
    get:
      x-yc-apigateway-integration:
        type: object_storage
        bucket: kt-frontend
        object: '{rest}'
        service_account_id: <sa-id>
  /:
    get:
      x-yc-apigateway-integration:
        type: object_storage
        bucket: kt-frontend
        object: 'index.html'
        service_account_id: <sa-id>
```

```bash
yc serverless api-gateway create --name kt --spec @api-gw.yaml
```

Получаем публичный URL `https://d5d<id>.apigw.yandexcloud.net`. Это и есть «ссылка для всех».

## Шаг 6. Custom domain (опционально)

Купить домен, добавить CNAME → выданному apigw-URL, прописать в `yc serverless api-gateway update --name kt --add-domain example.com`.

## Чек-лист безопасности

- [ ] API-ключ LLM **только** через Lockbox, не в .env коммита
- [ ] `RATE_LIMIT_PER_MIN=30` или ниже — защита от спама
- [ ] Healthz **публичный**, всё остальное по rate-limit
- [ ] `LLM_MAX_INPUT_CHARS=14000` — защита от prompt-injection с гигантскими контекстами
- [ ] Admin-API (`/api/v1/admin/*`) — закрыть basic-auth или убрать из API-Gateway, **или** добавить auth-middleware (текущий MVP без авторизации)

## Чего ещё не хватает

1. **Auth для admin-плана** — сейчас `/api/v1/admin/*` открыт всем. До публикации добавить басик-auth через middleware или вынести в отдельный API Gateway behind VPN.
2. **Persistent storage для events.jsonl/users/\*.json** — Serverless Container не имеет постоянной FS. Нужно подключить Object Storage volume или перейти на Managed PostgreSQL / DocumentDB.
3. **CI/CD** — GitHub Actions с `yc-action` для деплоя на push в master.
4. **Бакап mastery / events** — для production-нагрузки.

## Локальный prod-like запуск

Чтобы убедиться, что dev и prod дают одинаковое поведение, есть локальный gateway на Caddy (`Caddyfile` в корне):

```bash
# Терминал 1
LLM_API_KEY=sk-... uvicorn app.main:app --port 8000

# Терминал 2
cd frontend && npm run dev   # :5173

# Терминал 3
caddy run --config Caddyfile  # :8080 → объединяет

# Открыть
open http://localhost:8080
```

В этой конфигурации фронт обращается к `/api/...` (относительный путь) — тот же контракт, что и в prod.
