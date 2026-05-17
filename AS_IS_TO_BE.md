# Roadmap: ML-пайплайн «теория + банк → адаптивный тренажёр»

Стратегический документ. Описывает, во что превращаем проект, что меняем в k2-18, какие admin/trainer API нужны и в каком порядке всё это строить.

> **Статус на 2026-05-11**: Этап A полностью; Этап B шаги 5-6 + 10 готовы (strict pipeline + bank-RAG explain); Этап D шаги 15-17 готовы (events + BKT online + recommend v0 + mastery). Подробности в §10.

---

## 0. Цель

Платформа, на которую загружаешь:
- **bank** (главы / темы / задания / опции / правильные ответы) — XLSX или нормализованный JSON,
- **theory** — markdown учебника,
- (опционально) **exam manifest** — yaml с метаданными,

запускаешь пайплайн — получаешь **готовый адаптивный тренажёр** с графом знаний, BKT-мастерией, IRT-сложностью и AI-разборами.

Сейчас этот сценарий захардкожен под Базовый ФСФР. Хочется, чтобы был **multi-exam** (ФСФР, ЕГЭ/ОГЭ, CFA, любой школьный/проф курс с готовой структурой).

---

## 1. AS IS — что есть прямо сейчас

### 1.1. Артефакты в репо

| Путь | Что | Источник |
|---|---|---|
| [data/sources/fsfr_bazoviy_knowledge.xlsx](data/sources/fsfr_bazoviy_knowledge.xlsx) | банк: 13 глав / 68 тем / 2102 задачи / 8066 опций | ground truth |
| [theory_economics.md](theory_economics.md) | 3.8 MB markdown учебника | ground truth |
| [staging/slice_*.json](staging/) | 37 нарезок учебника по 15 KB | k2-18 шаг 1 |
| [out/ConceptDictionary.json](out/ConceptDictionary.json) | 758 концептов | k2-18 шаг 2 |
| [out/LearningChunkGraph_longrange.json](out/LearningChunkGraph_longrange.json) | граф 1211/2989 (chunks 384, concepts 697, assessments 130) | k2-18 шаги 3-5 |
| [frontend/public/exam-basic.json](frontend/public/exam-basic.json) | конвертированный банк (2.6 MB JSON) | `scripts/convert_bank.py` |

### 1.2. Что работает

- **Конвертер банка** [scripts/convert_bank.py](scripts/convert_bank.py) — XLSX → JSON, детерминированно, с дедупом дублей опций.
- **Frontend** — полный UX (онбординг, входной тест, дашборд `Тренажёр` с mastery-индикаторами, адаптивная сессия, пробные варианты, локальное per-theme mastery в `localStorage`).
- **Backend RAG-инфра** ([app/rag/](app/rag/)) — Chroma + embedder + reranker + клиент Yandex Eliza. Работоспособна.

### 1.3. Что НЕ работает / ограничения

| # | Проблема | Корень |
|---|---|---|
| 1 | k2-18 **извлекает** структуру (главы/темы) LLM-ом — галлюцинирует, не совпадает с XLSX | k2-18 рассчитан на «нет готовой структуры» |
| 2 | 130 Assessment графа — это пересказы LLM, не настоящие single-choice. Бэк-эндпоинт `/analyze_test` принимает их id и бесполезен для bank-вопросов | k2-18 |
| 3 | 904/2180 MENTIONS — авто с весом 0.35, шум | k2-18 longrange refiner |
| 4 | 61 концепт удалён дедупом, словарь не пересобран | дедуп шаг |
| 5 | Mastery — наивная эвристика `correct/asked`, без статмодели | фронт |
| 6 | Только один экзамен (ФСФР) — хардкод | архитектура |
| 7 | Нет admin-флоу для загрузки нового экзамена | нет |
| 8 | LLM-объяснения только для graph-вопросов, не для bank-вопросов | API расхождение |

---

## 2. TO BE — целевая система

### 2.1. Один абзац

**k2-18 остаётся**, но переключается в **strict-mode**: получает готовый банк и не извлекает структуру, а строит вокруг неё **граф знаний** (концепты, MD-секции, связи task↔concept, theme↔section). Сверху — **multi-exam admin API** для загрузки/управления и **trainer API** с `BKT + IRT + FSRS`. Фронт получает селектор экзамена и AI-разборы по bank-задачам.

### 2.2. Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                       ADMIN PLANE                                │
│  ┌──────────────┐    POST /admin/exams                          │
│  │ Admin UI     │ ─► POST /admin/exams/{id}/bank   (xlsx)       │
│  │  (мини-SPA)  │ ─► POST /admin/exams/{id}/theory (md)         │
│  └──────────────┘ ─► POST /admin/exams/{id}/ingest              │
│                  ─► GET  /admin/exams/{id}/runs/{run_id}/log    │
│                  ─► POST /admin/exams/{id}/publish              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PIPELINE (strict mode)                          │
│                                                                  │
│   bank.xlsx ──► convert_bank ──► bank.json (chapters/themes/    │
│                                            tasks/options)       │
│                                                                  │
│   theory.md ──► slice (k2-18) ──► slices/*.json                 │
│                                                                  │
│   slices ──► extract_concepts (k2-18) ──► concepts.json         │
│                                                                  │
│   concepts ──► dedup (k2-18 + улучшения) ──► concepts_clean.json│
│                                                                  │
│   concepts + bank ──► LLM link task→concepts ──► task_skills.json
│                                                                  │
│   slices + bank.themes ──► semantic link ──► theme_sections.json│
│                                                                  │
│   concepts ──► LLM extract prereq (per chapter) ──► edges.json  │
│                                                                  │
│   ВСЁ ──► assemble unified_graph ──► graph.json                 │
│                                                                  │
│   graph + slices ──► ingest to Chroma ──► chroma/<exam_id>/     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   STORAGE (per exam)                             │
│  data/exams/<exam_slug>/                                         │
│    ├── exam.yaml          (manifest: title, slug, version, ...) │
│    ├── bank.json          (нормализованный банк)                │
│    ├── theory.md          (исходный)                            │
│    ├── slices/*.json      (k2-18 slice output)                  │
│    ├── concepts.json      (k2-18 + LLM extra)                   │
│    ├── graph.json         (unified)                             │
│    ├── theme_sections.json (theme_code → md anchors)            │
│    └── chroma/            (vector index)                        │
│                                                                  │
│  data/db.sqlite (или postgres):                                  │
│    exams, ingest_runs, events, model_params, users(*)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TRAINER PLANE                                 │
│                                                                  │
│   GET  /exams                  (опубликованные)                  │
│   GET  /exams/{slug}           (структура + counts)              │
│   GET  /exams/{slug}/bank      (банк)                            │
│   POST /exams/{slug}/event     (запись ответа)                   │
│   POST /exams/{slug}/recommend (BKT+IRT+FSRS → next item)        │
│   POST /exams/{slug}/explain   (RAG + LLM разбор)                │
│   GET  /exams/{slug}/theme/{code} (статья теории по теме)        │
│                                                                  │
│              Frontend читает только trainer plane                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3. Что внутри strict-mode k2-18

Сейчас k2-18 — это цепочка: `slice → concepts → graph (chunks + concepts + assessments) → dedup → refiner`. Идея в том, что **strict-mode заменяет 3 шага** из 5:

| Шаг | Loose mode (текущий) | Strict mode (новый) |
|---|---|---|
| 1. Slice | разбить MD по 15K токенов | то же |
| 2. Extract concepts | LLM по тексту slice | **то же**, но с дополнительным контекстом: «темы этого slice» из bank |
| 3. Build graph | LLM генерит Chunks + Assessments + рёбра | **скип** — Chunk заменяем slice-id, Assessment берём из bank.tasks |
| 4. Dedup concepts | similarity-based | то же + перенос concept на максимально близкую `theme_code` из bank |
| 5. Refiner | LLM ищет долгие связи между chunks | заменяем на **LLM link task→concepts** + **prereq между concepts** |

Делать **обёртку** (`pipeline/strict.py`), которая дёргает нужные функции k2-18 как библиотеку. Форкать только то, что k2-18 не экспортирует.

### 2.4. Унифицированная схема graph.json

Расширяем существующий формат k2-18 LearningChunkGraph (один файл — много типов узлов и рёбер). Добавляем типы узлов из bank:

```jsonc
{
  "_meta": { "exam_slug": "...", "version": "...", "pipeline_mode": "strict" },
  "nodes": [
    { "id": "ch:1",          "type": "Chapter",  "num": 1, "name": "..." },
    { "id": "th:1.1",        "type": "Theme",    "chapter_id": 1, "code": "1.1", "name": "..." },
    { "id": "co:emission",   "type": "Concept",  "term": "Эмитент", "aliases": [...], "definition": "...", "theme_codes": ["1.1","3.2"] },
    { "id": "tk:1234",       "type": "Task",     "theme_code": "1.1", "task_text": "...", "answer_type": "single_choice", "options": [...], "ground_truth": ["4"], "difficulty_prior": 1 },
    { "id": "md:slice_001#h2-1", "type": "Section", "slice_id": "slice_001", "anchor": "h2-1", "text": "..." }
  ],
  "edges": [
    { "source": "ch:1",      "target": "th:1.1",        "type": "HAS_THEME" },
    { "source": "tk:1234",   "target": "co:emission",   "type": "TESTS_CONCEPT", "weight": 0.9 },
    { "source": "co:emission","target": "co:emission-types","type": "PREREQUISITE", "weight": 0.7 },
    { "source": "md:slice_001#h2-1", "target": "th:1.1", "type": "EXPLAINS_THEME", "weight": 0.8 },
    { "source": "co:emission","target": "th:1.1",       "type": "BELONGS_TO_THEME", "weight": 1.0 }
  ]
}
```

Узлы: `Chapter / Theme / Concept / Task / Section`. Рёбра: `HAS_THEME, HAS_TASK, TESTS_CONCEPT, BELONGS_TO_THEME, PREREQUISITE, ELABORATES, EXAMPLE_OF, EXPLAINS_THEME`.

Schema-валидация через JSON Schema лежит в `pipeline/schema/graph.schema.json`.

### 2.5. Polymorphic Task

`Task.answer_type` ∈ `{ single_choice, multiple_choice, true_false, numeric, fill_in_blank, ordering, matching, free_text }`. Для каждого типа — отдельный grader и фронт-виджет. В bank.json — `answer_type` уже есть, расширяем форматы `options`/`ground_truth` под каждый тип.

Текущий банк ФСФР полностью `single_choice` — но архитектурно поддерживаем все.

### 2.6. ML слой

| Подсистема | Где | Когда фитится |
|---|---|---|
| **IRT (β, α per task)** | offline, `pipeline/fit_irt.py` | при ingest + при ≥ N новых событий |
| **BKT (P_L0, P_T, P_G, P_S per skill)** | offline EM, `pipeline/fit_bkt.py` | при ≥ N новых событий, неделя |
| **BKT online update** | per-event на бэке | в реальном времени, в `/event` |
| **FSRS state per (user, skill)** | per-event | в реальном времени |
| **Policy /recommend** | бэк | по запросу |
| **Eval (held-out AUC)** | `pipeline/eval.py` | вручную / в CI |

Cold start: bootstrap β из `bank.difficulty_prior`, BKT-параметры из глобальных дефолтов (`P_L0=0.3, P_T=0.1, P_G=0.2, P_S=0.1`). Постепенно EM-фит.

---

## 3. Admin API — детали

### 3.1. Эндпоинты

```python
POST   /admin/exams                     # создать draft (slug, title)
GET    /admin/exams                     # список (все, включая draft)
GET    /admin/exams/{slug}              # детали
PATCH  /admin/exams/{slug}              # title/manifest
DELETE /admin/exams/{slug}              # удалить со всеми артефактами

# Артефакты
POST   /admin/exams/{slug}/bank         # multipart: XLSX или bank.json
POST   /admin/exams/{slug}/theory       # multipart: theory.md
POST   /admin/exams/{slug}/manifest     # exam.yaml (опц.)
GET    /admin/exams/{slug}/files        # перечень артефактов

# Пайплайн
POST   /admin/exams/{slug}/ingest       # body: {mode:"strict"|"loose", steps?: [...] }
                                        # запускает фоновый run, возвращает run_id
GET    /admin/exams/{slug}/runs         # история запусков
GET    /admin/exams/{slug}/runs/{id}    # статус + лог
GET    /admin/exams/{slug}/runs/{id}/log  (stream)  # SSE для лайв-лога
POST   /admin/exams/{slug}/runs/{id}/cancel

# Просмотр
GET    /admin/exams/{slug}/graph/summary   # counts, quality stats
GET    /admin/exams/{slug}/graph/concepts  # список с привязкой к темам
GET    /admin/exams/{slug}/graph/orphans   # node-orphans, недостающие связки
GET    /admin/exams/{slug}/quality         # отчёт о покрытии тем теорией

# Управление
POST   /admin/exams/{slug}/publish
POST   /admin/exams/{slug}/unpublish
POST   /admin/exams/{slug}/fit            # body: {kind:"irt"|"bkt"}  — переобучение моделей

# Сервис
POST   /admin/login                       # для прода — пока basic auth
GET    /admin/whoami
```

### 3.2. Background runs

Очередь — `redis + arq` или просто sqlite + thread-pool на старте (хватит). Каждый run — atomic write в `data/exams/<slug>/runs/<run_id>/log.txt` + JSON со статусом. SSE-эндпоинт стримит лог в admin UI.

### 3.3. Авторизация

MVP: HTTP Basic с одним admin-юзером из ENV (`ADMIN_USER`/`ADMIN_PASS`). Потом — нормальный JWT.

---

## 4. Trainer API — детали

```python
GET    /exams                           # только published
GET    /exams/{slug}                    # структура: counts + manifest
GET    /exams/{slug}/bank               # bank.json (был в /exam-basic.json)
GET    /exams/{slug}/theme/{code}       # markdown-статья + sources
GET    /exams/{slug}/chapter/{id}       # шапка + список тем

POST   /exams/{slug}/event              # body: {user_id, task_id, picked, is_correct, t}
POST   /exams/{slug}/recommend          # body: {user_id, count, exclude_recent?}
POST   /exams/{slug}/explain            # body: {task_id, picked_label, correct_label}

# Дашборд (на стороне сервера, если хотим перенести с фронта)
GET    /exams/{slug}/mastery/{user_id}  # вектор BKT mastery
```

Старые `/api/v1/analyze_test`, `/topics`, `/topic_dive` — deprecated, оставить под `?dev=1`.

---

## 5. Admin UI

Отдельный мини-SPA, route `/admin/*`, та же кодовая база на Vite. Экраны:

1. **Список экзаменов** — таблица: slug, title, status (`draft/ingesting/ready/error/published`), последний run.
2. **Создание экзамена** — slug + title + (опц.) clone from existing.
3. **Карточка экзамена**:
   - вкладка **Артефакты** — drag-and-drop загрузки bank.xlsx / theory.md / exam.yaml; история файлов.
   - вкладка **Пайплайн** — кнопка «Запустить ingest», выбор шагов, лайв-лог (SSE), история запусков.
   - вкладка **Качество** — counts по узлам/рёбрам, orphan-concepts, недопокрытые темы.
   - вкладка **Граф** — простая визуализация (Cytoscape.js) на сэмпле 200 нод.
   - вкладка **Модели** — статус IRT/BKT fit, последняя метрика AUC, кнопка refit.
   - вкладка **Публикация** — toggle publish / unpublish, ссылка на trainer URL.

UI должен быть unproductized — простой, но строгий: таблицы, формы, лог в `<pre>`. Стек тот же, что в основном фронте.

---

## 6. Multi-exam frontend (trainer)

На входе — селектор экзамена (онбординг → выбор курса). Все экраны принимают `exam_slug` и читают `GET /exams/{slug}/bank`. Локальный mastery становится `Record<exam_slug, MasteryStore>` в `localStorage` (или переезжает на бэк через `/event` + `/mastery/{user_id}`).

Изменения по экранам — поверх существующих:

| Экран | Что добавить |
|---|---|
| Onboarding | селектор экзамена после входа |
| Dashboard | `exam_slug` в URL/state, заголовок «Тренажёр: {exam_title}» |
| Entrance / Practice / Adaptive / Exam | использовать `bank` загруженный по slug |
| Theory (новый) | `GET /exams/{slug}/theme/{code}` |
| Settings (новый) | смена экзамена, экспорт прогресса, сброс mastery |

---

## 7. Изменения в k2-18

Не форкаем — пишем **обёртку** `pipeline/strict.py`, которая импортирует функции k2-18 как библиотеку. Список того, что нужно вытащить из k2-18:

| k2-18 функция | Используем как есть | Меняем |
|---|---|---|
| `slice_markdown` | ✅ | — |
| `extract_concepts_per_slice` | ✅ | передаём дополнительный контекст «темы slice из bank» через theme_sections |
| `dedup_concepts` | ✅ | + добавляем `theme_codes` aggregation |
| `build_graph` (Chunk + Concept + Assessment) | ❌ | заменяем своей сборкой `assemble_graph` |
| `longrange_refiner` | ❌ | заменяем `LLM link task↔concept` + `extract_prerequisites_per_chapter` |
| `auto_mentions` | ❌ | убираем — шум |

Если k2-18 не экспортирует функции отдельно — делаем мини-форк / PR upstream. Идеал — иметь k2-18 как pip-зависимость с публичным API.

---

## 8. ML pipeline scripts (новые)

| Скрипт | Назначение |
|---|---|
| `pipeline/strict.py` | главный orchestrator strict-mode (вызывает k2-18 + наши шаги) |
| `pipeline/link_tasks_to_concepts.py` | LLM-разметка `task → [concept_ids]` (батчами через Eliza) |
| `pipeline/link_theory_to_themes.py` | embedding-similarity + LLM-override; результат `theme_sections.json` |
| `pipeline/extract_prerequisites.py` | LLM `concept → [prereq_concept_ids]` per chapter |
| `pipeline/assemble_graph.py` | сборка `graph.json` из всех артефактов |
| `pipeline/fit_irt.py` | IRT 1PL/2PL по событиям, выход `model_params.irt` |
| `pipeline/fit_bkt.py` | BKT EM по событиям, выход `model_params.bkt` |
| `pipeline/eval.py` | AUC predict_correctness на held-out |

---

## 9. Storage layout

```
data/
├── db.sqlite                      # exams, ingest_runs, events, model_params
├── sources/                       # raw uploads (для аудита)
│   └── fsfr_bazoviy_knowledge.xlsx
└── exams/
    └── fsfr-basic/
        ├── exam.yaml              # манифест
        ├── bank.json              # из convert_bank
        ├── theory.md              # копия исходника
        ├── slices/                # k2-18 step 1
        ├── concepts.json          # k2-18 step 2-4
        ├── graph.json             # unified
        ├── theme_sections.json    # theme_code → md anchors
        ├── chroma/                # vector index
        ├── runs/<run_id>/
        │   ├── status.json
        │   └── log.txt
        └── models/
            ├── irt.json
            └── bkt.json
```

Frontend `public/exam-basic.json` уходит, заменяется `GET /exams/{slug}/bank`.

---

## 10. Roadmap (последовательно)

Минимум — то, что нужно сделать в этом порядке. Параллелить можно после п.3.

### Этап A — Multi-exam основа (1.5-2 дня) ✅

1. ~~**DB schema + миграции**~~ → пока не понадобилось; events живут как JSONL в `data/exams/{slug}/events.jsonl`, mastery в `users/{user_id}.json`. SQLite введём при необходимости multi-process. ✅ упрощено
2. **`Exam` repository + `AppContext.exams`** → [app/exams/registry.py](app/exams/registry.py). ✅
3. **Trainer API exam-aware** → `GET /exams`, `GET /exams/{slug}/bank` уже работают. ✅
4. **Frontend** → `loadBank()` через `/api/v1/exams/fsfr-basic/bank`. Селектор экзамена пока скрыт (один экзамен). ✅

После A: фронт работает через бэк, можно одной командой поднять второй экзамен (например, бутафорский «mini-test»), не трогая код.

### Этап B — Strict-mode pipeline (3-4 дня) — частично

5. **`app/pipeline/strict.py`** — orchestrator. ✅
6. **`app/pipeline/link_tasks_to_concepts.py`** — линкер через E5 embeddings (без LLM-rerank пока). ✅ — на полном банке 6306 связей, 141 сек.
7. **`pipeline/link_theory_to_themes.py`** — semantic similarity + LLM-rerank. ⚠️ pipeline (TODO)
8. **`pipeline/extract_prerequisites.py`** — LLM по главам. ⚠️ pipeline (TODO)
9. **`assemble_graph`** — встроено в `strict.py` (шаг 5). ✅
10. **`app/rag/ingest.py`** перевести на новые источники. ⚠️ бэк (TODO — пока используем существующие коллекции `md_chunks` + `graph_chunks` из старого ingest, работает для bank-explain)

После B: запуск `python -m pipeline.strict --exam fsfr-basic` собирает всё с нуля. Старый k2-18-loose остаётся как `--mode loose`.

### Этап C — Admin API + UI (2-3 дня)

11. **`/admin/exams`** CRUD + upload bank/theory. ⚠️ бэк
12. **Background runner** (sqlite-таблица + asyncio.Task / arq). Запуск `pipeline/strict.py` как subprocess, стрим лога в файл. ⚠️ бэк
13. **`/admin/exams/{slug}/runs/{id}/log`** через SSE. ⚠️ бэк
14. **Admin UI**: список + карточка + загрузка + лог. Без визуализации графа в MVP. ⚠️ фронт

После C: можно через UI загрузить новый XLSX + MD → запустить → получить тренажёр без правок кода.

### Этап D — Knowledge tracing (3-4 дня) — частично

15. **`/exams/{slug}/event`** через JSONL-лог + atomic write `users/{id}.json`. ✅ ([app/services/events.py](app/services/events.py))
16. **BKT online** ([app/exams/bkt.py](app/exams/bkt.py)) + **`/recommend`** v0 ([app/services/recommend.py](app/services/recommend.py)) — proximity к target_p=0.65 + Bernoulli-entropy + cooldown 12 задач. ✅
17. **`/exams/{slug}/explain`** — bank-RAG. ✅ ([app/services/bank_explain.py](app/services/bank_explain.py))
18. **Фронт «AI-разбор»** в `QuestionCard` через `ExplainBlock`. ✅
19. **`pipeline/fit_irt.py`** + `POST /admin/exams/{slug}/fit?kind=irt`. ⚠️ pipeline + бэк (TODO)
20. **`pipeline/fit_bkt.py`** EM-фит. ⚠️ pipeline (TODO)
21. **FSRS spaced repetition** в `/recommend`. ⚠️ бэк (TODO)
22. **`GET /exams/{slug}/mastery/{user_id}`** — concept/theme/chapter aggregate. ✅
23. **Frontend fire-and-forget `/event`** после каждого ответа. ✅

После D: реальная ML-петля. Параметры калибруются на накопленных событиях.

### Этап E — Quality, polishing (1-2 дня)

22. **`pipeline/eval.py`** — AUC predict_correctness на held-out splits. ⚠️ pipeline
23. **Admin: вкладка «Качество»** — orphan-concepts, темы без секций теории, темы с низким покрытием банка. ⚠️ фронт
24. **Удаление legacy graph-кода** на бэке и в `types.ts`. ⚠️ обе
25. **Теория** — экран `TheoryScreen` для bank-themes. ⚠️ фронт

---

## 11. Открытые вопросы

| # | Вопрос | Возможные ответы |
|---|---|---|
| 1 | Где живёт mastery в TO BE — фронт или бэк? | Фронт (приватность + offline) vs бэк (нужно для кросс-устройства + аналитики). MVP: **фронт + опциональная синхронизация на бэк через `/event`**. |
| 2 | Multi-user? | MVP: stub `user_id` из localStorage. Прод: OAuth/JWT после стабилизации. |
| 3 | Загрузка через UI или CLI? | Оба. `scripts/upload_exam.py` для админов + UI для нетехнических. |
| 4 | Хранилище — sqlite или postgres? | MVP: sqlite. Прод (multi-user, фит моделей): postgres. |
| 5 | Visualization графа в admin UI — Cytoscape? D3? | Cytoscape.js — стандарт для KG. На сэмпле 200 нод хватит. |
| 6 | k2-18 — форк или библиотека? | Сначала писать обёртку. Если k2-18 не открыт по нужным функциям — pull request upstream, fork как backup. |
| 7 | Polymorphic Task — все 8 типов сразу? | Нет. MVP: `single_choice` + `multiple_choice` + `numeric` + `free_text` (LLM-grader). Остальные позже. |
| 8 | Где живёт LLM-grader для `free_text`? | Бэк через Eliza, кэшируется по `(task_id, answer_hash)`. |

---

## 12. Что предлагаю сделать первым

Я бы стартовал с **Этапа A (multi-exam основа)** — он разблокирует всё остальное и его можно пилить за полтора дня. После него — **Этап B шаг 5-6** (orchestrator + linker task↔concept), потому что именно это снимает главную боль AS IS («130 кривых Assessment»).

Дальше — слой за слоем. Roadmap не обязан быть монолитным: после каждого этапа продукт остаётся в рабочем состоянии.

Скажи, с чего стартуем — и/или что докрутить в этом плане.
