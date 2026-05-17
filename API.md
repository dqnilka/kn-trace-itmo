# API — форматы запросов и ответов

API сервиса AI Knowledge Tracing. Все эндпоинты возвращают JSON (`Content-Type: application/json`).

> Базовый URL по умолчанию: `http://localhost:8000`
> Версионируемые эндпоинты — под префиксом `/api/v1`.
> Healthz — на корне (`/healthz`).

## Содержание

- [POST `/api/v1/analyze_test`](#post-apiv1analyze_test)
  - [Сценарий A: есть ошибки](#сценарий-a-есть-ошибки--errors_found)
  - [Сценарий B: всё верно](#сценарий-b-всё-верно--perfect_score)
- [GET `/api/v1/topic_dive`](#get-apiv1topic_dive)
- [GET `/api/v1/topics`](#get-apiv1topics)
- [GET `/healthz`](#get-healthz)
- [Глобальные коды ошибок](#глобальные-коды-ошибок)
- [Идентификаторы узлов графа](#идентификаторы-узлов-графа)

---

## POST `/api/v1/analyze_test`

Главный эндпоинт. Принимает результаты теста, возвращает либо план изучения по ошибкам, либо предложение углубиться в тему (если ответы все правильные).

### Запрос

| Поле                          | Тип    | Обязательное | Описание                                                                                |
| ----------------------------- | ------ | ------------ | --------------------------------------------------------------------------------------- |
| `user_id`                     | int    | ✅            | Идентификатор пользователя. Эхо-возвращается в ответе. Без персистентности в текущей версии. |
| `test_results`                | array  | ✅            | Массив результатов по каждому вопросу теста. Длина 1..100 (типично 20-25).              |
| `test_results[].question_id`  | string | ✅            | ID вопроса = ID Assessment-узла в графе (см. [формат ID](#идентификаторы-узлов-графа)). |
| `test_results[].is_correct`   | bool   | ✅            | `true` — пользователь ответил верно, `false` — ошибся.                                  |

#### Пример запроса (сокращённый)

```json
{
  "user_id": 12345,
  "test_results": [
    {"question_id": "theory_economics:q:284949:1", "is_correct": false},
    {"question_id": "theory_economics:q:316273:7", "is_correct": false},
    {"question_id": "theory_economics:q:451889:2", "is_correct": true}
  ]
}
```

Полный пример с 25 вопросами (3 неверных) — [`examples/scenario_a_request.json`](./examples/scenario_a_request.json).

### Сценарий A: есть ошибки → `errors_found`

Если хотя бы один `is_correct=false` — формируется итеративный план изучения.

#### Структура ответа

| Поле                                | Тип            | Описание                                                                                              |
| ----------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------- |
| `status`                            | `"errors_found"` | Признак сценария.                                                                                     |
| `user_id`                           | int            | Эхо.                                                                                                  |
| `total_questions`                   | int            | Сколько вопросов было в запросе.                                                                      |
| `correct_count`                     | int            | Сколько правильных.                                                                                   |
| `incorrect_count`                   | int            | Сколько неправильных = `len(study_plan)`.                                                             |
| `study_plan`                        | array          | По одному элементу на каждую ошибку.                                                                  |
| `study_plan[].failed_question_id`   | string         | ID вопроса из запроса.                                                                                |
| `study_plan[].question_text`        | string         | Полный текст вопроса (из узла графа).                                                                 |
| `study_plan[].related_concepts`     | string[]       | ID связанных Chunk и Concept узлов из BFS обхода (top-N по weighted score). Гарантия: каждый ID существует в графе. |
| `study_plan[].related_chunks`       | string[]       | Поднабор `related_concepts` — только узлы типа Chunk. Удобно для UI.                                  |
| `study_plan[].theory_content`       | string         | Markdown-текст объяснения. Минимум 200 символов. Структура зависит от типа вопроса (см. ниже).        |
| `study_plan[].sources`              | array          | До 10 источников, использованных для генерации (см. ниже).                                            |
| `study_plan[].generation_mode`      | `"llm"` / `"extractive"` | `llm` в production; `extractive` — fallback для unit-тестов с `SKIP_LLM=1`.                  |

#### Структура `theory_content`

Всегда Markdown с нумерованными разделами:

1. **Что проверял вопрос** — 1-2 предложения.
2. **Ключевые понятия** — список с определениями.
3. **Подробное объяснение** *или* **Разбор вариантов** *(для multi-choice)* — основной разбор.
4. **На что обратить внимание** — типичные ошибки/подсказки.

Для multiple-choice вопросов (детектируется по словам «Варианты:», нумерации, римским цифрам) автоматически активируется секция «Разбор вариантов» с поэлементным разбором (правильный ответ + почему остальные неверны).

Для compound-вопросов (≥5 разных Concept-узлов на L1 BFS) подмешивается инструкция «честно говорить о пробелах», поэтому в тексте могут встречаться явные фразы вида *«по подтеме X в предоставленном контексте недостаточно материала»* — это feature, не bug: студент знает, где надо добрать материал из других источников.

#### Структура `sources[]`

| Поле        | Тип    | Описание                                                                                       |
| ----------- | ------ | ---------------------------------------------------------------------------------------------- |
| `node_id`   | string | Для `node_type="MdChunk"` — синтетический ID (`md:NNNNN`); иначе ID реального узла графа.      |
| `node_type` | enum   | `"Chunk"` / `"Concept"` / `"Assessment"` / `"MdChunk"`.                                        |
| `score`     | float  | В диапазоне (0, 1]. Финальный скор после graph-boost и cross-encoder rerank.                   |
| `snippet`   | string | Первые 400 символов исходного текста источника (с многоточием в конце, если обрезано).         |

#### Полный пример ответа (сокращённый)

```json
{
  "status": "errors_found",
  "user_id": 12345,
  "total_questions": 25,
  "correct_count": 22,
  "incorrect_count": 3,
  "study_plan": [
    {
      "failed_question_id": "theory_economics:q:284949:1",
      "question_text": "Блок тестовых вопросов по доверительному управлению...",
      "related_concepts": [
        "theory_economics:p:deyatelnost-po-upravleniyu-cennymi-bumagami",
        "theory_economics:p:kvalificirovannyy-investor",
        "theory_economics:p:registrator",
        "theory_economics:c:239655"
      ],
      "related_chunks": [
        "theory_economics:c:239655"
      ],
      "theory_content": "## 1. Что проверял вопрос\nВопрос проверял знание блоков по доверительному управлению...\n\n## 2. Ключевые понятия\n- **Регистратор** — ...\n\n## 3. Подробное объяснение\n...\n\n## 4. На что обратить внимание\n- ...",
      "sources": [
        {
          "node_id": "theory_economics:c:284944",
          "node_type": "Chunk",
          "score": 0.9715,
          "snippet": "Обзорный фрагмент: тесты по реестрам, депозитариям..."
        },
        {
          "node_id": "md:00715",
          "node_type": "MdChunk",
          "score": 0.7140,
          "snippet": "Регистраторами на рынке ценных бумаг обычно..."
        }
      ],
      "generation_mode": "llm"
    }
  ]
}
```

Полный реальный пример — [`examples/scenario_a_response.json`](./examples/scenario_a_response.json) (≈18 KB JSON; 3 study_plan item).

### Сценарий B: всё верно → `perfect_score`

Если все `is_correct=true`.

| Поле               | Тип      | Описание                                                                  |
| ------------------ | -------- | ------------------------------------------------------------------------- |
| `status`           | `"perfect_score"` | Признак сценария.                                                |
| `user_id`          | int      | Эхо.                                                                       |
| `total_questions`  | int      | Сколько вопросов было.                                                     |
| `message`          | string   | Подсказка пользователю (`"Выберите тему для углубления"` по умолчанию).    |
| `available_topics` | string[] | Top-N тем (default 8) — это display-имена. Используются как `topic_name` в [`/topic_dive`](#get-apiv1topic_dive). |

#### Пример

```json
{
  "status": "perfect_score",
  "user_id": 12345,
  "total_questions": 25,
  "message": "Выберите тему для углубления",
  "available_topics": [
    "Производные инструменты",
    "Ценная бумага",
    "Рынок ценных бумаг",
    "Индоссамент",
    "Облигация",
    "Эмитент",
    "Депозитарий",
    "Договор репо"
  ]
}
```

### Возможные ошибки

| HTTP | Причина                                                                                  |
| ---- | ---------------------------------------------------------------------------------------- |
| 422  | Валидация pydantic: `test_results` пустой / >100, отсутствуют поля, неверный тип.        |
| 404  | `question_id` не найден в графе (или это не Assessment-узел). Detail: `Unknown question_id: ...`. |
| 502  | Ошибка LLM (Eliza недоступна, истёк токен, и т.п.). Detail: `analyze_test failed: ...`.  |

---

## GET `/api/v1/topic_dive`

Топ-5 «сложных» вопросов по выбранной теме.

### Параметры запроса

| Параметр     | Тип    | Обязательный | Описание                                                                                              |
| ------------ | ------ | ------------ | ----------------------------------------------------------------------------------------------------- |
| `topic_name` | string | ✅            | Имя темы из ответа `/topics` или `available_topics`. Регистр и пробелы по краям не важны; есть substring-match как graceful fallback. |

### Ответ

| Поле                                        | Тип      | Описание                                                                  |
| ------------------------------------------- | -------- | ------------------------------------------------------------------------- |
| `topic_name`                                | string   | Каноническое имя найденной темы (то, что в `topics.json`).                |
| `matched_concept_ids`                       | string[] | До 50 концептов, входящих в тему (членов k-means кластера).               |
| `questions`                                 | array    | До 5 вопросов, отсортированных по score (TESTS+MENTIONS) и difficulty.    |
| `questions[].question_id`                   | string   | ID Assessment-узла.                                                       |
| `questions[].text`                          | string   | Полный текст вопроса.                                                     |
| `questions[].difficulty`                    | int / null | Сложность (1-5) из узла графа.                                          |
| `questions[].related_concept_ids`           | string[] | До 5 ID концептов из текущей темы, прямо связанных с вопросом.            |

### Пример запроса

```bash
curl -G --data-urlencode 'topic_name=Облигация' \
     http://localhost:8000/api/v1/topic_dive
```

### Пример ответа

```json
{
  "topic_name": "Облигация",
  "matched_concept_ids": [
    "theory_economics:p:obligaciya",
    "theory_economics:p:kuponnyy-dohod",
    "theory_economics:p:emitent-obligaciy"
  ],
  "questions": [
    {
      "question_id": "theory_economics:q:242015:1",
      "text": "#### Рынок ценных бумаг\n\n##### Функционирование финансового рынка\n\nВопрос: Финансовый рынок представ...",
      "difficulty": 3,
      "related_concept_ids": [
        "theory_economics:p:obligaciya"
      ]
    }
  ]
}
```

### Возможные ошибки

| HTTP | Причина                                                                  |
| ---- | ------------------------------------------------------------------------ |
| 422  | Отсутствует `topic_name`.                                                |
| 404  | Тема не найдена. Detail: `Unknown topic: <name>`.                        |

---

## GET `/api/v1/topics`

Список всех тем (k-means кластеров концептов). Удобно для построения UI выбора темы.

### Ответ

| Поле                | Тип      | Описание                                  |
| ------------------- | -------- | ----------------------------------------- |
| `topics`            | array    | Все темы.                                 |
| `topics[].topic_id` | int      | ID кластера (0..N_TOPICS-1).              |
| `topics[].name`     | string   | Display-имя — primary term центрального концепта. |
| `topics[].size`     | int      | Сколько концептов входит в тему.          |

### Пример

```json
{
  "topics": [
    {"topic_id": 0, "name": "Производные инструменты", "size": 100},
    {"topic_id": 1, "name": "Ценная бумага",           "size": 70},
    {"topic_id": 2, "name": "Рынок ценных бумаг",      "size": 65}
  ]
}
```

---

## GET `/healthz`

Проверка готовности сервиса. Возвращает 200 если всё ОК, 503 если что-то не готово.

### Ответ

| Поле                  | Тип            | Описание                                                                  |
| --------------------- | -------------- | ------------------------------------------------------------------------- |
| `status`              | `"ok"` / `"degraded"` | Сводный статус.                                                  |
| `graph_loaded`        | bool           | Граф успешно прочитан в память.                                           |
| `vector_store_ready`  | bool           | Все 3 коллекции Chroma непустые.                                          |
| `llm_configured`      | bool           | `SOY_TOKEN` присутствует.                                                 |
| `nodes`               | int            | Сколько узлов в графе.                                                    |
| `edges`               | int            | Сколько рёбер.                                                            |
| `topics`              | int            | Сколько тем сгенерировано.                                                |

### Пример (production)

```json
{
  "status": "ok",
  "graph_loaded": true,
  "vector_store_ready": true,
  "llm_configured": true,
  "nodes": 1211,
  "edges": 2989,
  "topics": 15
}
```

---

## Глобальные коды ошибок

| HTTP   | Когда                                                                                                                |
| ------ | -------------------------------------------------------------------------------------------------------------------- |
| `200`  | Успех.                                                                                                               |
| `404`  | Запрошенная сущность не найдена в графе/в темах.                                                                     |
| `422`  | Pydantic-валидация запроса.                                                                                          |
| `502`  | Ошибка LLM или другого внешнего сервиса при обработке запроса.                                                       |
| `503`  | Сервис не готов (например, ingest не выполнен — стартовый guard в `lifespan`). На практике сервис в этом случае не поднимется. |

Формат тела ошибки соответствует FastAPI default:
```json
{ "detail": "Unknown question_id: theory_economics:q:does_not_exist:1" }
```

---

## Идентификаторы узлов графа

ID имеют форму `<slug>:<type>:<offset>[:<index>]`:

| Тип        | Префикс | Пример                                  | Что означает                              |
| ---------- | ------- | --------------------------------------- | ----------------------------------------- |
| Assessment | `q`     | `theory_economics:q:284949:1`           | Тестовый вопрос                            |
| Chunk      | `c`     | `theory_economics:c:116313`             | Учебный фрагмент текста                    |
| Concept    | `p`     | `theory_economics:p:rynok-cennykh-bumag`| Доменный концепт (термин)                  |
| MdChunk    | `md`    | `md:00715`                              | Re-chunk из `theory_economics.md` (в RAG, **не** в графе) |

Получить актуальные `question_id` для тестов — посмотреть `examples/scenario_a_request.json` или прогнать:

```bash
python -c "
import json
g = json.load(open('out/LearningChunkGraph_longrange.json'))
ids = [n['id'] for n in g['nodes'] if n['type']=='Assessment'][:10]
print(*ids, sep='\n')
"
```

---

## Стабильность контракта

Поля схемы документированы в `app/api/schemas.py` (pydantic-модели). Любое изменение API должно сопровождаться:
1. Изменением модели в `schemas.py`.
2. Обновлением [API.md](./API.md) и [README.md](./README.md).
3. Обновлением `scripts/validate_response.py` (валидатор инвариантов).
4. Обновлением unit-тестов в `tests/test_services.py`.
5. Прогоном `./scripts/e2e.sh` для подтверждения.
