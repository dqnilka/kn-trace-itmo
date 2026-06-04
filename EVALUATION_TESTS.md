# Запуск тестов и оценки качества

## Требования

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (менеджер пакетов)

## Установка зависимостей

```bash
uv sync
uv pip install pytest scikit-learn ruff
```

## Запуск тестов модуля оценки

Все 107 тестов полностью автономны — не требуют API-ключей, LLM, интернета или предварительного запуска проекта.

```bash
uv run pytest tests/evaluation/ -v
```

### Что проверяют тесты

| Файл | Что тестирует | Количество |
|---|---|---|
| `test_bkt_metrics.py` | BKT: монотонность, AUC-ROC, Log-Loss, RMSE | 15 |
| `test_fsrs_metrics.py` | FSRS: монотонность стабильности, калибровка ECE | 9 |
| `test_recommender_metrics.py` | Рекомендер: ECE, Brier, Hit@5, NDCG@5, Coverage, Filters | 17 |
| `test_explanation_metrics.py` | Объяснения: структура (4 секции), парсер | 14 |
| `test_summary_metrics.py` | Сводки: формат, длина, покрытие концептов | 16 |
| `test_runner_report.py` | Интеграция: runner + генерация .md отчёта | 16 + 20 |

## Генерация отчёта о качестве

```bash
# Автономный режим (без LLM)
uv run python -m evaluation --output evaluation_report.md

# С LLM-as-judge (требуется API-ключ)
LLM_API_KEY=your-key uv run python -m evaluation --output evaluation_report.md --with-llm
```

Отчёт содержит таблицу метрик с порогами и статусами ✅ PASS / ⚠️ WARN / ❌ FAIL.

## Запуск через Docker

```bash
# Сборка
docker build -f Dockerfile.eval -t akt-eval .

# Автономный отчёт (без LLM)
docker compose -f docker-compose.eval.yml up eval

# С LLM-judge (ключи берутся из .env)
docker compose -f docker-compose.eval.yml run eval-with-llm

# Произвольные аргументы (например --with-llm)
docker compose -f docker-compose.eval.yml run eval-shell --with-llm --exam-dir /path/to/exam
```

> **Важно:** для LLM-judge используется сервис `eval-with-llm`, а не `eval --with-llm`. Сервис `eval` игнорирует аргументы после `up`.

### Yandex Cloud

Задай переменные в `.env` или `environment` в compose:

```yaml
environment:
  LLM_API_KEY: "<токен>"
  LLM_BASE_URL: "https://llm.api.cloud.yandex.net/foundationModels/v1"
  LLM_MODEL: "yandexgpt-lite"
```

## Линтинг

```bash
uv run ruff check evaluation/ tests/evaluation/
```

## Структура тестовых данных

Синтетические данные лежат в `evaluation/fixtures/test_exam/` и соответствуют формату реальных данных проекта:

- `bank.json` — 30 задач, 5 тем, 2 главы
- `graph.json` — 52 узла (Chapter, Theme, Task, Concept), 101 ребро
- `task_skills.jsonl` — 90 связей задача→концепт
- `events.jsonl` — 189 событий от 10 пользователей с разными паттернами
- `explanations/` — 10 объяснений (5 корректных, 5 с нарушениями структуры)
- `summaries/` — 10 сводок тем (5 корректных, 5 с нарушениями формата)
