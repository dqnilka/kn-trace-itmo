# AI Knowledge Tracing — adaptive FSFR exam trainer

Адаптивный тренажёр для подготовки к экзамену ФСФР (Федеральная служба по финансовым рынкам). Студенту даётся реальный банк из ~2100 задач; система отслеживает мастерство через Bayesian Knowledge Tracing (BKT), пишет в учебнике именно те темы, где есть пробелы, и генерирует AI-разбор каждой ошибки на основе RAG-поиска по учебнику.

**Демо**: фронт + бэк уже задеплоены на Yandex Cloud →
https://d5d05aesrv8vtemcc0ga.628pfjdx.apigw.yandexcloud.net

---

## Что внутри

- **Граф знаний**: 2700+ узлов (13 глав → 68 тем → 2100 задач → 550 концептов) с типизированными связями `TESTS_CONCEPT`, `PREREQUISITE`, `BELONGS_TO_THEME` и т.д. Собирается своим `strict`-пайплайном из bank.xlsx + theory.md.
- **RAG**: ChromaDB + E5 embedder (multilingual-e5-small) + cross-encoder reranker (mMiniLMv2). Учебник в 1.8 MB markdown режется на ~1100 chunks.
- **BKT + FSRS**: онлайн-обновление per-concept mastery после каждого ответа; spacing-stability per (user, skill).
- **Адаптивный recommender**: следующая задача выбирается по proximity к target_p=0.65 + Bernoulli information gain + штраф за слабые prerequisites.
- **AI-разбор** ошибок и автоматическое summary темы через любой OpenAI-совместимый LLM (OpenAI / DeepSeek / OpenRouter / YandexGPT). Кэш на диске → 100% hit rate после первой генерации, экономия токенов.
- **Multi-exam**: поддержка нескольких серий ФСФР (Базовая + 1.0…7.0) через admin-плейн.
- **Production-ready инфра**: Terraform → Yandex Cloud (Container Registry + Serverless Container + Object Storage + API Gateway + Lockbox).

---

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11 / FastAPI / pydantic-settings / ChromaDB / sentence-transformers / OpenAI SDK |
| Frontend | TypeScript / React 18 / Vite / `react-markdown` + `rehype-sanitize` |
| ML | E5 embeddings, cross-encoder reranker, BKT (4-параметрический), FSRS-lite |
| Storage | ChromaDB (vector) + JSONL events + per-user JSON (mastery) + localStorage (frontend) |
| Infra | Docker, Docker Compose, Caddy (local gateway), Terraform, Yandex Cloud, GitHub Actions |

---

## Требования

- **Python** 3.11 (3.12 тоже работает; pyproject ограничивает `>=3.11,<3.13`)
- **Node.js** 18+ для фронта
- **Docker** для prod-сборки (опционально для dev)
- **LLM API-ключ** OpenAI-совместимого провайдера (опционально — без него работает в `SKIP_LLM=true` режиме с extractive fallback)

Для деплоя в Yandex Cloud дополнительно: `terraform >= 1.5`, `yc` CLI, `aws` CLI.

---

## Быстрый старт (локально)

```bash
git clone <repo>
cd kn-trace-itmo

# 1. .env
cp .env.example .env
# отредактировать: либо вставить LLM_API_KEY, либо оставить SKIP_LLM=true

# 2. Backend (Python)
python -m venv .venv
.venv\Scripts\activate          # Windows
# или: source .venv/bin/activate # macOS/Linux
pip install -e .

# 3. Прогреть ChromaDB (один раз, ~30-60 сек)
python -m app.rag.ingest

# 4. Запустить бэк
uvicorn app.main:app --port 8000 --reload

# 5. Frontend (в другом терминале)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Vite-конфиг проксирует `/api/*` и `/healthz` на `localhost:8000`, так что фронт автоматически видит бэк.

### Локальный production-shape (единый порт)

Чтобы dev был идентичен prod (один публичный URL, всё через gateway), есть `Caddyfile`:

```bash
# Терминал 1: backend
uvicorn app.main:app --port 8000

# Терминал 2: frontend
cd frontend && npm run dev

# Терминал 3: gateway
caddy run --config Caddyfile
# → http://localhost:8080  (единая точка входа)
```

---

## Production deploy (Yandex Cloud)

Полная пошаговая инструкция: [`terraform/SETUP.md`](terraform/SETUP.md).

Кратко:

```bash
# 1. terraform.tfvars — заполнить cloud_id, folder_id, sa_key_file, llm_api_key
cd terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars

# 2. Поднять инфру (~5 минут)
terraform init
terraform apply

# 3. Собрать prod-образ + push + deploy + загрузить frontend
cd ..
bash scripts/deploy.sh
```

После завершения `terraform output public_url` напечатает публичную HTTPS-ссылку.

### CI/CD

`.github/workflows/deploy.yml` пересобирает + redeploys при push в `master`. Нужно положить 8 secrets в GitHub Settings — список в `terraform/SETUP.md`, шаг 8.

---

## Примеры использования API

После старта бэка:

```bash
# Health-check (показывает budget-meter, число задач, статус коллекций)
curl http://localhost:8000/healthz | jq

# Список экзаменов
curl http://localhost:8000/api/v1/exams | jq

# Bank задач конкретного экзамена
curl http://localhost:8000/api/v1/exams/fsfr-basic/bank | jq '.tasks | length'

# AI-разбор задачи (если LLM включён — иначе вернёт extractive)
curl -X POST http://localhost:8000/api/v1/exams/fsfr-basic/explain \
  -H 'Content-Type: application/json' \
  -d '{"task_id": 1, "picked_label": "2"}' | jq

# Рекомендация следующих задач для пользователя
curl -X POST http://localhost:8000/api/v1/exams/fsfr-basic/recommend \
  -H 'Content-Type: application/json' \
  -d '{"user_id": 42, "count": 5, "target_p": 0.65}' | jq

# Mastery конкретного пользователя
curl http://localhost:8000/api/v1/exams/fsfr-basic/mastery/42 | jq
```

Полная справка по API: [API.md](API.md).

---

## Структура проекта

```
kn-trace-itmo/
├── app/                    # Backend (Python / FastAPI)
│   ├── main.py             # Entry point (FastAPI app)
│   ├── deps.py             # AppContext (singletons)
│   ├── api/                # HTTP layer: v1 routes + pydantic schemas
│   ├── admin/              # Admin API: exam CRUD + ingest runs
│   ├── core/               # config, logging, budget meter (cache + rate-limit)
│   ├── exams/              # ExamRegistry, StrictGraph, BKT + FSRS
│   ├── graph/              # Legacy KG stubs (kept for compat)
│   ├── pipeline/           # strict-mode pipeline (bank → graph)
│   │                       # link_tasks_to_concepts, extract_prerequisites,
│   │                       # link_theory_to_themes
│   ├── rag/                # Embeddings, vectorstore, retriever, reranker, generator
│   └── services/           # bank_explain, theme_summary, events, recommend, viewer
│
├── frontend/               # React + TypeScript
│   ├── src/
│   │   ├── App.tsx         # Корневой routing (14 экранов)
│   │   ├── screens/        # Onboarding, ExamSeries, Entrance, Dashboard,
│   │   │                   # Practice, AdaptiveSession, LearningPath, Theory,
│   │   │                   # ExamVariant, MockOutcome, FinalStretch,
│   │   │                   # RealExamPrep, Results, Wip
│   │   ├── components/     # QuestionCard, ExplainBlock, KnowledgeHeatmap,
│   │   │                   # PostExamModal, SafeMarkdown, ErrorBoundary, HealthBadge
│   │   ├── state/          # user, mastery, bank (localStorage)
│   │   ├── api.ts          # Backend client с AbortController + timeout
│   │   └── admin/          # Admin UI (отдельный bundle)
│   └── vite.config.ts
│
├── data/                   # Runtime artifacts (gitignored)
│   ├── chroma/             # Vector store
│   └── exams/<slug>/       # bank.json, graph.json, theme_sections.json
│
├── out/                    # k2-18 artifacts: LearningChunkGraph, ConceptDictionary
├── staging/                # k2-18 slice intermediate output
├── vendor/k2-18/           # Vendored k2-18 viewer + schema
├── scripts/                # build_example_request, convert_bank, deploy.sh,
│                           # validate_response, e2e.sh
├── tests/                  # pytest (некоторые сейчас сломаны после strict-перехода)
│
├── terraform/              # Yandex Cloud IaC
│   ├── main.tf             # Container + Bucket + API Gateway + Lockbox + SAs
│   ├── api-gateway.yaml    # Routing spec
│   ├── SETUP.md            # Пошаговая инструкция для первого deploy
│   └── terraform.tfvars.example
│
├── .github/workflows/      # CI/CD
│   └── deploy.yml          # push в master → auto-deploy в Yandex Cloud
│
├── Dockerfile              # Dev image (multi-stage, без baked data)
├── Dockerfile.prod         # Prod image (baked Chroma + HF cache + exams)
├── docker-compose.yml      # Local dev stack
├── Caddyfile               # Локальный single-port gateway (:8080)
├── theory_economics.md     # 1.8 MB учебник по рынку ценных бумаг (источник для RAG)
│
├── CLOUD_DEPLOY.md         # Архитектура и стоимость прод-деплоя
├── QUICKSTART.md           # Локальный e2e через Docker Compose
├── API.md                  # Полная справка по REST API
├── AS_IS_TO_BE.md          # Roadmap + дизайн-документ
└── pyproject.toml          # Python deps + tool config
```

---

## Конфигурация (env)

Полный список в `.env.example`. Самые важные:

| Переменная | Default | Зачем |
|---|---|---|
| `LLM_API_KEY` | — | Ключ OpenAI-совместимого провайдера. Без него поставить `SKIP_LLM=true` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint провайдера |
| `LLM_MODEL` | `gpt-4o-mini` | Имя модели |
| `LLM_MAX_TOKENS` | `1200` | Hard-cap на output |
| `LLM_MAX_INPUT_CHARS` | `14000` | Hard-cap на input (защита от prompt-injection с гигантскими контекстами) |
| `LLM_CACHE_ENABLED` | `true` | Disk-cache для bank_explain (детерминированных запросов) |
| `RATE_LIMIT_PER_MIN` | `30` | Per-IP rate limit |
| `SKIP_LLM` | `false` | Если `true` — `/explain` возвращает extractive fallback без обращения к LLM |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | E5 embedder |
| `ENABLE_RERANKER` | `true` | Cross-encoder rerank поверх embedding-retrieval |

---

## Документация

| Файл | Что |
|---|---|
| [API.md](API.md) | Полная спецификация REST API: эндпоинты, схемы, коды ошибок, примеры |
| [QUICKSTART.md](QUICKSTART.md) | Запуск через Docker Compose + e2e-тест |
| [AS_IS_TO_BE.md](AS_IS_TO_BE.md) | Архитектурный roadmap (от текущего состояния до целевого) |
| [CLOUD_DEPLOY.md](CLOUD_DEPLOY.md) | Архитектура Yandex Cloud deploy + расчёт стоимости |
| [terraform/SETUP.md](terraform/SETUP.md) | Пошаговая инструкция: создание Service Account, заполнение tfvars, terraform apply |
| [AGENTS.md](AGENTS.md) | Правила работы AI-ассистентов в репо |

---

## Контроль расходов

Реальное приложение с LLM-вызовами может неприятно ужалить по токенам. Что встроено:

- **Disk cache** для bank_explain и theme_summary — детерминированные вызовы (один task_id + picked_label) после первой генерации отдаются бесплатно.
- **Budget meter** в `/healthz` показывает `input_tokens`, `output_tokens`, `calls`, `cached_hits` за uptime процесса.
- **Hard-cap** на длину промпта (`LLM_MAX_INPUT_CHARS=14000`) и ответа (`LLM_MAX_TOKENS=1200`).
- **Rate limit** middleware: 30 req/min/IP.
- **SKIP_LLM=true** — полный bypass LLM с extractive fallback (для CI / dev / smoke-проверки инфры).

Для DeepSeek (`deepseek-chat` ≈ $0.27/1M output) после прогрева кэша демо для группы из 20 студентов укладывается в ~$1 за сессию.

---

## Тесты

```bash
pytest -v
```

> ⚠️ Часть тестов на текущем стейте сломана из-за миграции с legacy k2-18 KnowledgeGraph на strict-pipeline (`tests/conftest.py` импортирует устаревшие типы). См. [AS_IS_TO_BE.md §10](AS_IS_TO_BE.md) — Этап E «Quality, polishing».

Frontend type-check + build:
```bash
cd frontend
npx tsc --noEmit       # должно вернуть 0
npm run build          # vite build → dist/
```

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

Учебник `theory_economics.md` и банк задач — собственность правообладателей; используются в учебных целях.
