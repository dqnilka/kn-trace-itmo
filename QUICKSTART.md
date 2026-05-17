# Quickstart — установка, запуск, тестирование

Этот документ — компактное руководство «с нуля до зелёного e2e».
Полный обзор системы → [README.md](./README.md). Форматы запросов/ответов → [API.md](./API.md).

---

## Что нужно перед началом

| Требование          | Версия / комментарий                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| **Docker**          | `docker compose v2` (тестировано на Docker Desktop 29.4.0)                                          |
| **macOS / Linux**   | На macOS работает через Docker Desktop; CA bundle собирается с Keychain                             |
| **`SOY_TOKEN`**     | Токен авторизации Yandex Eliza, экспортирован в shell **ДО** запуска                                |
| **`jq`, `curl`**    | Нужны для `scripts/e2e.sh` (`brew install jq` на macOS)                                             |
| **uv** *(опц.)*     | Только для дев-режима без Docker (`brew install uv`)                                                |
| **Артефакты k2-18** | `out/LearningChunkGraph_longrange.json`, `out/ConceptDictionary.json`, `theory_economics.md` — есть |
| **Свободно ~3 GB**  | Под Docker volumes (HF cache модели + chroma)                                                       |

> ⚠️ На macOS Docker Desktop корректно работает `network_mode: host` (используется для доступа к внутренней сети Yandex Eliza). Если `*.yandex.net` не резолвится — проверьте, что ноут в корпоративной сети / VPN.

---

## Сценарий 1. Полный e2e «одной командой» (рекомендуется)

```bash
# 1. SOY-токен из текущего окружения (никогда не коммитим)
export SOY_TOKEN=...  # значение из вашего рабочего окружения

# 2. Полный e2e: build + ingest (если нужно) + up + POST + jq-проверки + tear-down
./scripts/e2e.sh
```

Что происходит:
1. Pre-flight: проверка `SOY_TOKEN`, `jq`, `curl`, `docker`.
2. Создание `.env` из `.env.example`, если ещё нет.
3. `scripts/prepare_ca_bundle.sh` собирает CA bundle (`data/ca-bundle.pem`) с корпоративным сертификатом из macOS Keychain.
4. Если volume `chroma_data` пуст — запускается `docker compose --profile ingest run --rm ingest` (~5-7 минут на первый раз: качается e5-small + cross-encoder + строятся эмбеддинги).
5. `docker compose up -d api`, ожидание `/healthz` (до 60s).
6. `POST /api/v1/analyze_test` с `examples/scenario_a_request.json` → ответ сохраняется в `examples/scenario_a_response.json`.
7. **jq-инварианты + полный референциальный валидатор** (`scripts/validate_response.py`).
8. Дополнительные проверки: `GET /api/v1/topics`, `GET /api/v1/topic_dive?...`, perfect-score сценарий.
9. По умолчанию — `docker compose down`.

Флаги:
- `./scripts/e2e.sh --keep` — оставить контейнер запущенным после прогона.
- `./scripts/e2e.sh --rebuild` — снести volume и заново выполнить ingest.

---

## Сценарий 2. Ручной запуск через Docker

```bash
# .env (один раз)
cp .env.example .env
# Подставьте свой токен (или используйте экспорт из shell — env_file подхватит):
echo "SOY_TOKEN=$SOY_TOKEN" >> .env

# CA bundle (один раз)
./scripts/prepare_ca_bundle.sh

# Build
docker compose build api

# Ingest (один раз, ~5-7 минут на первый запуск)
docker compose --profile ingest run --rm ingest

# Запуск API
docker compose up -d api
curl -fsS http://localhost:8000/healthz | jq

# Тест сценария A (есть ошибки)
curl -X POST http://localhost:8000/api/v1/analyze_test \
     -H 'Content-Type: application/json' \
     -d @examples/scenario_a_request.json | jq

# Тест сценария B (perfect)
curl -X POST http://localhost:8000/api/v1/analyze_test \
     -H 'Content-Type: application/json' \
     -d @examples/scenario_a_request_perfect.json | jq

# Список тем
curl -fsS http://localhost:8000/api/v1/topics | jq

# Topic dive
curl -G --data-urlencode 'topic_name=Облигация' \
     http://localhost:8000/api/v1/topic_dive | jq

# Остановить
docker compose down
```

---

## Сценарий 3. Дев-режим (без Docker)

Удобно для итераций по коду/тестам.

```bash
# Один раз
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -e .

# CA bundle (один раз)
./scripts/prepare_ca_bundle.sh

# Ingest (один раз; ~30-60 секунд на E5-small с GPU/CPU)
.venv/bin/python -m app.rag.ingest

# Запуск API
LLM_CA_BUNDLE=$PWD/data/ca-bundle.pem \
    .venv/bin/uvicorn app.main:app --reload --port 8000

# В другом терминале:
curl -X POST http://localhost:8000/api/v1/analyze_test \
     -H 'Content-Type: application/json' \
     -d @examples/scenario_a_request.json | jq
```

---

## Тестирование

### Unit-тесты (без сети, ~2 секунды)

```bash
# Все 54 теста
.venv/bin/python -m pytest -v

# Один файл
.venv/bin/python -m pytest tests/test_graph.py -v

# Один тест
.venv/bin/python -m pytest tests/test_reranker.py::test_mock_reranker_promotes_token_overlap_match -v
```

### Что проверяет каждый файл

| Файл                            | Что покрывает                                                                              |
| ------------------------------- | ------------------------------------------------------------------------------------------ |
| `test_graph.py`                 | Загрузчик, BFS глубины 2, веса рёбер, двунаправленные TESTS, поиск концепта по term/alias  |
| `test_topics.py`                | K-means кластеризация, имя темы по центроиду, сериализация topics.json                     |
| `test_vectorstore.py`           | ChromaDB add/search, cosine_topk                                                           |
| `test_md_chunker.py`            | Разбиение по H2/H3, метаданные section_path/char_offset                                    |
| `test_question_detection.py`    | `detect_multiple_choice` (по Варианты:/нумерации/римским), `extract_correct_answer`        |
| `test_extract_options.py`       | Парсинг опций (numeric/roman) с защитой от дублирования из-за «Ответ:»                     |
| `test_low_content_filter.py`    | Фильтрация коротких концептов из related_concepts и графовой инъекции                      |
| `test_boost_and_dedup.py`       | `boost_score` без насыщения, Jaccard tokens, константы порогов                             |
| `test_retriever.py`             | Базовый retrieve с graph-grounding                                                         |
| `test_retriever_extra.py`       | Дедупликация md ↔ graph, per-option extra_queries, no-saturation в pipeline                |
| `test_reranker.py`              | Identity/Mock/CrossEncoder rerankers, min-max нормализация, blend-формула, интеграция      |
| `test_generator_extractive.py`  | Extractive-режим (без LLM-вызова)                                                          |
| `test_services.py`              | Сценарий A с ошибками, perfect_score, unknown question, topic_dive                         |

### E2E-тест (Docker + реальная LLM)

```bash
./scripts/e2e.sh
```

Проверяет:
1. Healthz возвращает `graph_loaded=true, vector_store_ready=true, llm_configured=true`.
2. POST `/analyze_test` с 25 вопросами (3 неверных) → HTTP 200.
3. **JSON-инварианты** (jq):
   - `status == "errors_found"`
   - `study_plan` ровно 3 элемента
   - каждый item содержит `failed_question_id`, непустые `related_concepts` и `sources`, `theory_content >= 200` символов
4. **Референциальная целостность** (`scripts/validate_response.py`):
   - все `related_concepts` ID существуют в графе
   - все `sources.node_id` (кроме MdChunk) существуют в графе
5. `GET /api/v1/topics` возвращает >1 темы.
6. `GET /api/v1/topic_dive?topic_name=<первая тема>` возвращает HTTP 200, ровно 5 вопросов.
7. POST `/analyze_test` с perfect_score → `status="perfect_score"`, есть `available_topics`.

Артефакт после прогона: `examples/scenario_a_response.json` — реальный JSON-ответ системы.

### Ручная инспекция качества

```bash
# Структурный summary
jq '.study_plan | map({
    failed_question_id,
    related: (.related_concepts|length),
    sources: (.sources|length),
    theory_len: (.theory_content|length),
    mode: .generation_mode
  })' examples/scenario_a_response.json

# Полный текст одного study-plan элемента
jq -r '.study_plan[0].theory_content' examples/scenario_a_response.json

# Сравнение версий (сохранённые baseline'ы)
diff <(jq '.study_plan[0].theory_content' examples/scenario_a_response.before_fix.json) \
     <(jq '.study_plan[0].theory_content' examples/scenario_a_response.json)
```

---

## Конфигурация (env)

Полный список — в `.env.example`. Самые часто меняемые:

| Переменная             | Default                                          | Зачем                                                            |
| ---------------------- | ------------------------------------------------ | ---------------------------------------------------------------- |
| `SOY_TOKEN`            | (обязательно)                                    | Токен Yandex Eliza                                               |
| `LLM_MODEL`            | `gpt-5.4-nano`                                   | Модель LLM                                                       |
| `LLM_BASE_URL`         | `https://api.eliza.yandex.net/raw/openai/v1`     | Endpoint Eliza (`/raw/...`!)                                     |
| `EMBEDDING_MODEL`      | `intfloat/multilingual-e5-small`                 | Bi-encoder                                                       |
| `ENABLE_RERANKER`      | `true`                                           | Включить cross-encoder; `false` экономит ~150MB и ~200ms/запрос  |
| `RERANKER_MODEL`       | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`     | Cross-encoder model                                              |
| `RERANKER_TOP_K_IN`    | `20`                                             | Сколько кандидатов скармливаем CE                                |
| `RERANKER_TOP_K_OUT`   | `10`                                             | Сколько источников возвращаем после CE                           |
| `RERANKER_SCORE_BLEND` | `0.5`                                            | Доля CE-score в финальной смеси (0=только retrieval, 1=только CE) |
| `N_TOPICS`             | `15`                                             | Кластеры для perfect_score / topic_dive                          |
| `GRAPH_BFS_DEPTH`      | `2`                                              | Глубина обхода графа от Assessment                               |

---

## Типичные проблемы

### `SOY_TOKEN is not set` при старте контейнера

Не экспортирован в shell перед `docker compose`. Проверьте:
```bash
echo ${SOY_TOKEN:+OK} ${#SOY_TOKEN}
```

### `Connection error` / `CERTIFICATE_VERIFY_FAILED`

CA bundle отсутствует или устарел:
```bash
./scripts/prepare_ca_bundle.sh
docker compose down
docker compose up -d api
```

### `/healthz` долго не отвечает в первый раз

Первый старт качает E5-small (~470 MB) и cross-encoder (~150 MB). Подождите 1-2 минуты или посмотрите логи:
```bash
docker compose logs -f api
```

### Volume `chroma_data` запиаст после смены параметров

```bash
docker compose down -v   # снести volumes
./scripts/e2e.sh --rebuild
```

### Прогон долго работает (~30 секунд на 3 ошибки)

Это нормально: 3 LLM-запроса × ~6s + reranker setup + retrieve. Ускорение:
- `ENABLE_RERANKER=false` → −5s
- параллельные LLM-вызовы (не реализовано, см. roadmap)
- кэш LLM-ответов (не реализован, см. roadmap)

---

## Что можно улучшить (Roadmap)

Не реализовано в текущей версии, но имеет смысл добавить:

| #   | Что                                          | Эффект                                       | Сложность |
| --- | -------------------------------------------- | -------------------------------------------- | --------- |
| 1   | Параллельные LLM-вызовы для study_plan items | latency 30s → 8s                             | S         |
| 2   | LLM response cache (TTL)                     | повторные вопросы — instant                  | S         |
| 3   | Метрики p50/p95 в `/healthz`                 | observability                                | XS        |
| 4   | Структурный валидатор формы LLM-ответа       | re-prompt при поломанном Markdown            | M         |
| 5   | Параметр `depth` в API                       | UI-флексибильность                           | XS        |
| 6   | Учёт `difficulty` в ranking chunks           | сложнее = чаще релевантнее                   | XS        |
| 7   | Streaming-ответы (SSE)                       | UX: токен-за-токеном                         | M         |
| 8   | Persistence пользователей и истории          | track learning progress                      | L         |
| 9   | Pre-baked Docker image с уже сделанным ingest | мгновенный cold start                        | M         |
| 10  | Re-ranker на BAAI/bge-reranker-v2-m3         | +5-10% к качеству, но +400MB                 | XS        |
