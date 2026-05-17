import { useMemo } from 'react'
import SafeMarkdown from '../components/SafeMarkdown'

/**
 * Узлы f1-f5 (fail) и s1-s4 (success) диаграммы fsfr-user-flow v2.
 *
 * Показывается сразу после `ExamVariantScreen` через колбэк `onOutcome`.
 * Под «фейлом» мокаем «персональное письмо AI» (узел f3) + 5-7-дневная пауза
 * (узел f4). Под «успехом» — режим закрепления (узел s2) + подтверждающий
 * mock через 3-5 дней (узел s3 → s4).
 */

const AI_LETTER_MOCK = `Дорогой студент,

я внимательно посмотрел твой пробный экзамен. Ты подошёл к нему ответственно — это видно по тому, что ты дошёл до конца и не сдался на сложных вопросах.

**Что получилось хорошо.** Ты уверенно отвечаешь на вопросы по структуре рынка ценных бумаг — те же определения, которые мы прорабатывали неделю назад, ты вспомнил без подсказок. Это надёжная база, на которой будем расти дальше.

**Где мы пока проседаем.** Самые частые ошибки — в разделах про деривативы и доверительное управление. Это не глупость — там действительно много пересекающихся понятий: брокер, дилер, доверительный управляющий, форекс-дилер. Их легко путать, и я добавил в твой план дополнительные карточки именно с разделением этих ролей.

**План на ближайшие 5-7 дней.** Не нужно сейчас снова идти на пробный — это даст ту же ошибку. Лучше: 15 минут практики каждый день по слабым главам, плюс flashcard-дрилл на 5 минут утром. Через неделю встретимся на подтверждающем варианте.

Ты ближе к экзамену, чем кажется. Просто несколько локальных пробелов.

— AI-наставник`

export type MockOutcomeMode = 'fail' | 'success'

export default function MockOutcomeScreen({
  mode,
  pct,
  onPracticeWeak,
  onScheduleConfirm,
  onBack,
  onFinalStretch,
}: {
  mode: MockOutcomeMode
  pct: number
  onPracticeWeak: () => void
  onScheduleConfirm: () => void
  onBack: () => void
  onFinalStretch: () => void
}) {
  const dateOfNext = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() + (mode === 'fail' ? 6 : 4))
    return d
  }, [mode])

  if (mode === 'fail') {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← на дашборд
          </button>
        </div>
        <div className="screen-body narrow">
          <div className="trophy">📚</div>
          <h1 className="screen-title">Не совсем получилось ({pct}%)</h1>
          <p className="screen-subtitle">
            Это нормальный этап подготовки — теперь у нас есть точные данные,
            где доработать. Ниже — авто-план и личное письмо от AI-наставника.
          </p>

          <section className="outcome-section">
            <h2 className="section-title">Авто-план на 3 слабейшие главы</h2>
            <ol className="outcome-plan">
              <li>
                <strong>День 1-2.</strong> Прочитать теорию по самой слабой
                главе (режим «Только главное», ~5 минут), решить 10 задач из
                этого раздела.
              </li>
              <li>
                <strong>День 3-4.</strong> Перейти к следующему слабому разделу
                — той же схеме: теория → практика.
              </li>
              <li>
                <strong>День 5.</strong> Flashcard-дрилл по карточкам, которые
                система автоматически создала из твоих ошибок.
              </li>
              <li>
                <strong>День 6-7.</strong> Микс-практика по всем 3 главам.
                Подтверждающий mock через 7 дней.
              </li>
            </ol>
          </section>

          <section className="outcome-section ai-letter">
            <h2 className="section-title">Письмо от AI-наставника</h2>
            <SafeMarkdown>{AI_LETTER_MOCK}</SafeMarkdown>
          </section>

          <section className="outcome-section pause-card">
            <div className="pause-emoji">⏳</div>
            <div className="pause-body">
              <div className="pause-title">Пауза 5-7 дней до следующего mock</div>
              <div className="pause-sub">
                Следующий пробный — {dateOfNext.toLocaleDateString('ru-RU')}. До
                него — только практика и теория. Перепрохождение прямо сейчас
                даст ту же ошибку.
              </div>
            </div>
          </section>

          <div className="actions-row" style={{ marginTop: 24 }}>
            <button className="pill pill-primary big" onClick={onPracticeWeak}>
              Начать практику по слабым главам →
            </button>
          </div>
        </div>
      </div>
    )
  }

  // success: режим закрепления + подтверждающий mock через 3-5 дней
  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← на дашборд
        </button>
      </div>
      <div className="screen-body narrow">
        <div className="trophy">🏆</div>
        <h1 className="screen-title">Отличный результат! ({pct}%)</h1>
        <p className="screen-subtitle">
          Это очень хороший знак — ты прошёл проходной порог на пробном. До
          уверенной сдачи ещё один контрольный шаг.
        </p>

        <section className="outcome-section">
          <h2 className="section-title">Режим закрепления</h2>
          <ul className="outcome-plan">
            <li>
              Практика только по главам, где у тебя пока меньше 80% mastery —
              чтобы выровнять «слабые края».
            </li>
            <li>Один flashcard-дрилл утром, 5 минут.</li>
            <li>
              Через {Math.ceil((dateOfNext.getTime() - Date.now()) / 86400000)}{' '}
              {''}дня — подтверждающий mock. Если он тоже 80%+, открываем режим
              финишной прямой.
            </li>
          </ul>
        </section>

        <section className="outcome-section pause-card">
          <div className="pause-emoji">📅</div>
          <div className="pause-body">
            <div className="pause-title">
              Подтверждающий mock: {dateOfNext.toLocaleDateString('ru-RU')}
            </div>
            <div className="pause-sub">
              Запомним дату — за день до пришлём напоминание. Если второй mock
              тоже 80%+, активируется Final Stretch.
            </div>
          </div>
        </section>

        <div className="actions-row" style={{ marginTop: 24 }}>
          <button className="pill" onClick={onScheduleConfirm}>
            Запланировать подтверждающий
          </button>
          <button className="pill pill-primary big" onClick={onFinalStretch}>
            Сразу финишная прямая → (демо)
          </button>
        </div>
      </div>
    </div>
  )
}
