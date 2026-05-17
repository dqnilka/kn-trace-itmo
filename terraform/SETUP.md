# Yandex Cloud setup — пошаговая инструкция

После этого: один `terraform apply` поднимает всё; один `bash scripts/deploy.sh` выкатывает первую версию; публичный URL вида `https://d5d<id>.apigw.yandexcloud.net` готов.

Общее время: **~30 минут** (15 на клики в Console, 15 на сборку и push образа).

---

## Шаг 0. Что нужно ДО старта

- Аккаунт Yandex Cloud (https://console.cloud.yandex.ru). У вас уже есть — отлично.
- Billing account (создаётся при первом логине). Без него ресурсы не создадутся.
- API-ключ публичного LLM-провайдера. Рекомендации:
  - **DeepSeek** — `deepseek-chat` ≈ $0.27/1M output tokens (≈ 25 ₽/M). На $1k хватит на годы.
  - **OpenAI gpt-4o-mini** — ≈ $0.6/1M output. Чуть дороже, но качество выше.
  - **OpenRouter** — единый key для любого provider.
- Установлены локально:
  - `terraform >= 1.5` — https://developer.hashicorp.com/terraform/downloads
  - `docker` — Docker Desktop у вас уже есть
  - `yc` CLI — https://cloud.yandex.com/docs/cli/quickstart (один `curl ... | bash`)
  - `aws` CLI — `pip install awscli` (для загрузки фронта в bucket)

---

## Шаг 1. Узнать `cloud_id` и `folder_id`

Открой https://console.cloud.yandex.ru.

В **левом верхнем углу** есть селектор «Облако > Каталог». Под каждым из них есть `ID`, начинающийся с `b1g...`. Запомни оба.

> 💡 Альтернативно: запусти `yc init` (если уже стоит yc CLI) — он спросит и сохранит оба ID.

---

## Шаг 2. Создать «deployer» service account

В Console:

1. **IAM → Сервисные аккаунты → Создать сервисный аккаунт**
2. Имя: `kt-deployer`
3. Роли в этом каталоге:
   - `editor` (на каталог) — достаточно для всех ресурсов из terraform
4. Создать
5. Открыть созданный SA → **Создать новый ключ → Создать авторизованный ключ → JSON**
6. Сохранить файл как `terraform/kt-deployer-key.json` (этот путь уже в `.gitignore`)

> ⚠️ Файл с ключом — секрет. Никогда не коммитить.

---

## Шаг 3. Получить LLM API-ключ

Выбери провайдера и зарегистрируйся:

| Провайдер | Где взять ключ | Цена | Прим. |
|---|---|---|---|
| **DeepSeek** | https://platform.deepseek.com/api_keys | `deepseek-chat` $0.27/1M output | Самый дешёвый |
| **OpenAI** | https://platform.openai.com/api-keys | `gpt-4o-mini` $0.6/1M output | Стандарт |
| **OpenRouter** | https://openrouter.ai/keys | зависит от модели | Хочешь Claude/Llama — здесь |

Скопируй ключ — пригодится в шаге 5.

---

## Шаг 4. Подготовить chroma и базу данных локально

В Serverless Container нет persistent storage, поэтому в Docker-образ запекаем уже готовый chroma + bank/graph экзамена.

```bash
# Локально, в корне проекта:
docker compose --profile ingest run --rm ingest
```

Это создаст `data/chroma/` (~30 MB) и положит туда коллекции `graph_chunks`, `graph_concepts`, `md_chunks`. Если у вас уже chroma готов (а она готова — мы делали ingest ранее), этот шаг можно пропустить.

`data/exams/fsfr-basic/` уже на месте (мы используем его для бэка).

---

## Шаг 5. Заполнить `terraform.tfvars`

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Открой `terraform/terraform.tfvars` и заполни:

```hcl
cloud_id    = "b1g..."                       # из шага 1
folder_id   = "b1g..."                       # из шага 1
sa_key_file = "./kt-deployer-key.json"       # из шага 2

llm_api_key  = "sk-..."                      # из шага 3
llm_base_url = "https://api.deepseek.com/v1" # или openai.com / openrouter.ai
llm_model    = "deepseek-chat"

bucket_name = "kt-frontend-yourname-2026"    # глобально уникальное!
```

`bucket_name` обязан быть уникальным во всём Yandex Cloud — добавь к нему свой ник или дату.

---

## Шаг 6. `terraform apply`

```bash
cd terraform
terraform init
terraform plan        # ревью: что создастся
terraform apply       # подтверди 'yes'
```

Создастся (5-7 минут):
- 1 Container Registry
- 2 Service Accounts (container runner + bucket admin)
- 5 IAM-привязок
- 1 Lockbox secret + version
- 1 Serverless Container (пустой, без образа пока)
- 1 Object Storage bucket
- 1 API Gateway

В конце увидишь outputs. Запомни особенно:
- `public_url` — твой публичный домен
- `container_registry_id` — для push образа
- `container_id` — для revision deploy

---

## Шаг 7. Первый deploy

```bash
cd ..                  # вернулся в корень
bash scripts/deploy.sh
```

Это:
1. Соберёт `Dockerfile.prod` (~10 минут — torch + модели + chroma)
2. Запушит образ в Container Registry
3. Применит новую revision к Serverless Container
4. Соберёт фронт (`npm run build`)
5. Синхронизирует `frontend/dist/` в bucket
6. Сделает smoke `curl /healthz`

После завершения зайди на **public_url** — должен показать Onboarding.

---

## Шаг 8. (Опционально) Настроить CI/CD через GitHub Actions

Если хочешь авто-деплой при push в `master`:

1. В репозитории на GitHub → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Откуда взять |
|---|---|
| `YC_SA_KEY_FILE` | содержимое `kt-deployer-key.json` целиком |
| `YC_CLOUD_ID` | `cloud_id` |
| `YC_FOLDER_ID` | `folder_id` |
| `YC_CR_ID` | `terraform output -raw container_registry_id` |
| `YC_CONTAINER_ID` | `terraform output -raw container_id` |
| `YC_BUCKET` | `terraform output -raw bucket_endpoint` |
| `YC_BUCKET_AK` | `terraform output -raw bucket_access_key` |
| `YC_BUCKET_SK` | `terraform output -raw bucket_secret_key` |

2. Запушь в master — `.github/workflows/deploy.yml` запустится автоматически.

---

## Ротация LLM-ключа

```bash
cd terraform
# Поменяй llm_api_key в terraform.tfvars
terraform apply
# → создастся новая Lockbox version
# Контейнер автоматически подхватит — секрет инжектится в env при каждом старте
```

---

## Удаление всего

```bash
cd terraform
terraform destroy
```

Снесёт всё, кроме SA `kt-deployer` (его создавали руками).

---

## Типичные проблемы

### `terraform apply`: error "billing account is suspended"
Зайди в Console → Billing → активируй / положи денег.

### `docker push`: denied
Не сделал `yc container registry configure-docker`. Скрипт `deploy.sh` делает это сам.

### `/healthz` → 502 после deploy
Контейнер ещё прогревается (~30 сек на загрузку моделей из baked HF cache).
Через минуту повтори. Если упорно 502:
```bash
yc serverless container logs --name kt-app --since 5m
```

### LLM возвращает 401
Проверь Lockbox version:
```bash
yc lockbox secret get kt-app-llm-api-key
yc lockbox payload get-version <version-id>
```

### Цена убегает
Проверь budget meter:
```bash
curl https://<public_url>/healthz | jq '.budget'
# input_tokens / output_tokens растут — посмотри cached_hits.
# Низкий cached_hits означает кэш не работает: проверь LLM_CACHE_DIR
# на наличие persistent storage. В Serverless Container — нет persistent
# storage, поэтому cache теряется при cold start.
```

При большой нагрузке — рассмотри переход на Compute VM с persistent disk
или вынеси cache в Object Storage / DocumentDB.

---

## Структура файлов

```
terraform/
├── main.tf                    # все ресурсы
├── variables.tf               # переменные с описаниями
├── outputs.tf                 # что печатается после apply
├── api-gateway.yaml           # spec routing
├── terraform.tfvars.example   # шаблон значений
├── terraform.tfvars           # ваши значения (gitignored)
├── kt-deployer-key.json       # SA key (gitignored)
├── .gitignore
└── SETUP.md                   # этот файл

Dockerfile.prod                # production image с baked chroma + models
scripts/deploy.sh              # one-shot deploy
.github/workflows/deploy.yml   # CI/CD
```
