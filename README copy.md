# AI Knowledge Tracing

Backend для образовательного приложения подготовки к тесту ФСФР: знания пользователя моделируются как обход образовательного графа знаний (артефакты фреймворка [k2-18](https://github.com/zebrr/k2-18)), теория извлекается через RAG из учебника `theory_economics.md`, итоговое объяснение синтезируется LLM (Yandex Eliza, OpenAI-совместимое API).

📖 **Быстрый старт и тестирование** → см. [QUICKSTART.md](./QUICKSTART.md)
📋 **Форматы запросов и ответов** → см. [API.md](./API.md)

---

## Что делает

- **`POST /api/v1/analyze_test`** — принимает результаты теста (20–25 вопросов). Для каждого неверного ответа:
  1. Находит вопрос в графе (`Assessment`).
  2. **BFS глубины 2** по связям `TESTS / MENTIONS / PREREQUISITE / ELABORATES / EXAMPLE_OF / REFER_BACK` с весами по приоритетам (PREREQUISITE и ELABORATES — самые «жирные»). `TESTS` обходится в обе стороны.
  3. **Гибридный retrieval:** vector search (Chroma + sentence-transformers `intfloat/multilingual-e5-small`) по трём коллекциям (`graph_chunks`, `graph_concepts`, `md_chunks`); узлы из BFS получают дополнительный graph-boost (без насыщения).
  4. **Cross-encoder reranker** (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) переранжирует top-20 → top-10 финальных источников.
  5. **Per-option mini-retrieve** для multiple-choice вопросов: отдельный поиск по каждому варианту ответа.
  6. **LLM-генерация структурированного объяснения** (`gpt-5.4-nano` via Eliza) — строго на основе извлечённого контекста; для multi-choice автоматически добавляется overlay «Разбор вариантов»; для compound-вопросов — overlay про честную диагностику пробелов.
  7. Возвращает `study_plan` со ссылками на реальные `node_id` графа.

  Если ошибок нет — возвращает `perfect_score` и список крупных тем для углубления.

- **`GET /api/v1/topic_dive?topic_name=...`** — топ-5 «сложных» вопросов по выбранной теме.
- **`GET /api/v1/topics`** — список доступных тем (k-means кластеризация концептов по эмбеддингам, имя кластера = центральный концепт по degree).
- **`GET /healthz`** — статус готовности (граф загружен, векторное хранилище заполнено, LLM настроен).

## Архитектура

```
client ─▶ FastAPI ─▶ AnalyzeService ─┬─▶ KnowledgeGraph (BFS depth=2, weighted)
                                     │
                                     ├─▶ Retriever
                                     │     ├─ E5 embedder (query/passage prefixes)
                                     │     ├─ Chroma: graph_chunks + graph_concepts + md_chunks
                                     │     ├─ Graph-boost (additive, no saturation)
                                     │     ├─ Per-option mini-retrieve (MC questions)
                                     │     ├─ md/graph dedup (Jaccard tokens ≥ 0.7)
                                     │     └─ Cross-encoder reranker (optional)
                                     │
                                     └─▶ Generator (Yandex Eliza /raw/openai/v1, gpt-5.4-nano)
                                           ├─ Base prompt (Что проверял / Понятия / Объяснение / На что обратить)
                                           ├─ Multiple-choice overlay (Разбор вариантов)
                                           └─ Compound-topic overlay (честная диагностика пробелов)
```

## Структура проекта

```
app/
├── api/             # FastAPI router + pydantic-схемы (v1.py, schemas.py)
├── core/            # config (env, pydantic-settings), logging
├── graph/           # KnowledgeGraph: loader.py, knowledge_graph.py, topics.py
├── rag/             # embeddings.py, vectorstore.py, md_chunker.py,
│                    # ingest.py, retriever.py, reranker.py, generator.py
├── services/        # analyze.py, topic_dive.py
├── deps.py          # AppContext (singleton, lifespan), DI helpers
└── main.py          # FastAPI app
scripts/
├── prepare_ca_bundle.sh        # macOS: собрать CA bundle с Yandex CA
├── build_example_request.py    # Генерация examples/scenario_a_request.json
├── e2e.sh                      # Полный e2e-прогон через Docker
└── validate_response.py        # Семантическая валидация ответа
tests/                          # 54 unit-теста, без сети
out/                            # Артефакты k2-18 (input)
examples/                       # Готовые JSON для тестов
data/                           # ChromaDB, topics.json, ca-bundle.pem (gitignored)
```

## Ключевые технические решения

### Граф знаний
- Загрузка артефактов k2-18 напрямую (без runtime-зависимости от фреймворка).
- BFS глубины 2 с весами рёбер (PREREQUISITE=1.0, ELABORATES=0.9, TESTS=0.7, ...).
- `TESTS` обходится в обе стороны — в реальных данных ~5% таких рёбер идут `Chunk → Assessment`.
- Score узла = max по путям ($\prod$ priority\_weight × edge\_weight).

### RAG
- **Двухуровневый корпус**: чанки графа (точное соответствие узлам) + re-chunking `theory_economics.md` по H2/H3 (восполняет ~65% теории, не попавшей в граф).
- **Эмбеддинги**: `intfloat/multilingual-e5-small` с `query: ` / `passage: ` префиксами.
- **Graph-boost без насыщения**: `boosted = base + 0.25 × (1 − base)` — сохраняет порядок внутри boost'нутой группы (раньше всё схлопывалось в 1.0).
- **Дедупликация md ↔ graph**: Jaccard token-overlap ≥ 0.7 → md_chunk выбрасывается как дубль.
- **Per-option mini-retrieve**: для MC-вопросов делается отдельный vector search по каждому варианту → точные определения.
- **Cross-encoder reranking**: переранжировка top-20 → top-10 с min-max нормализованной смесью CE-score и retrieval-score (blend=0.5).

### LLM (Yandex Eliza)
- OpenAI SDK с `base_url=https://api.eliza.yandex.net/raw/openai/v1` (формат `/raw` возвращает ответ без проксирующего конверта).
- Bearer-аутентификация через `SOY_TOKEN` (берётся из ENV, никогда не пишется в код/файлы).
- macOS keychain → `data/ca-bundle.pem` через `scripts/prepare_ca_bundle.sh`.
- Без LLM-fallback: если `SOY_TOKEN` не задан, приложение падает на старте.

### Темы (Scenario B)
- K-means над эмбеддингами концептов (`n_clusters=15`).
- Имя темы = primary term концепта, ближайшего к центроиду (с tie-breaker'ом по degree).
- Кэшируется в `data/topics.json`.

### Quality-overlays для LLM
- **Multiple-choice detection**: regex по `Варианты:` / нумерованным/римским опциям → overlay «Разбор вариантов».
- **Correct-answer extraction**: `Ответ:` строка передаётся в промпт явно.
- **Compound-question detection**: ≥5 разных Concept-узлов на L1 BFS → overlay про честное упоминание непокрытых подтем.

### Инфраструктура
- **Docker compose** с `network_mode: host` (нужен для доступа к корпоративной сети Yandex).
- **CPU-only torch** в образе (избегаем nvidia-* зависимостей под arm64).
- **Идемпотентный ingest**: stamp по hash файлов + параметрам — повторный запуск пропускается.
- Разделение `api` / `ingest` сервисов через docker compose profiles.

## Тесты

**54 unit-теста** — без сети, без Docker, ~2 секунды на полный прогон:

```bash
.venv/bin/python -m pytest -v
```

Покрытие:
- Загрузка артефактов k2-18 и работа с графом
- BFS-обход с весами, обработка двунаправленных рёбер
- Кластеризация концептов и сериализация тем
- ChromaDB add/search через DeterministicHashEmbedder
- Re-chunking markdown
- Multiple-choice detection, extract_options, extract_correct_answer
- Low-content node filtering
- Graph-boost (no saturation) + token-overlap dedup
- Per-option mini-retrieve
- Cross-encoder reranker (mock + интеграция)
- Extractive generator (без LLM)
- Полный сервисный слой (analyze + topic_dive) с детерминированными embeddings

E2E-тест с реальной LLM и Docker — `./scripts/e2e.sh`.

## История качества (по итерациям)

| Итерация               | Unit-тесты | E2E | Заметные улучшения                                                                                                              |
| ---------------------- | ---------- | --- | ------------------------------------------------------------------------------------------------------------------------------- |
| v1: базовая система    | 23         | ✅   | Все эндпоинты работают, ответ строгий и без галлюцинаций                                                                        |
| v2: MC + low-content   | 33         | ✅   | Появилась секция «Разбор вариантов», compound-overlay, фильтр пустых концептов                                                  |
| v3: boost + dedup + MC | 47         | ✅   | Graph-boost без насыщения, дедупликация md/graph, per-option mini-retrieve. **Item 1 теперь точно объясняет, что не так с вариантом 2** |
| v4: cross-encoder      | **54**     | ✅   | Cross-encoder reranker с настраиваемым blend. **Item 0 (compound) теперь честно диагностирует пробелы** по подтемам             |

## Что можно улучшить дальше

См. список в [QUICKSTART.md → Roadmap](./QUICKSTART.md#что-можно-улучшить-roadmap).

## Лицензия / контакты

Internal POC.
