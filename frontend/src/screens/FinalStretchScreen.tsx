import { useState } from 'react'

/**
 * Узлы fs1-fs5 диаграммы: «Финишная прямая» — 14 дней до экзамена.
 *
 * MVP-мок: на экране нет «настоящих» данных — даты экзамена нет в системе.
 * Запоминаем дату в localStorage; считаем дни до неё; показываем разную
 * структуру за разное количество дней.
 */

const EXAM_DATE_KEY = 'akt:examDate'

function loadExamDate(): Date | null {
  try {
    const raw = localStorage.getItem(EXAM_DATE_KEY)
    return raw ? new Date(raw) : null
  } catch {
    return null
  }
}
function saveExamDate(d: Date): void {
  try {
    localStorage.setItem(EXAM_DATE_KEY, d.toISOString())
  } catch {
    // ignore
  }
}

export default function FinalStretchScreen({
  onBack,
  onReady,
  onRealExam,
}: {
  onBack: () => void
  onReady: () => void
  onRealExam: () => void
}) {
  const [examDate, setExamDate] = useState<Date | null>(() => loadExamDate())
  const [draft, setDraft] = useState<string>(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return d.toISOString().slice(0, 10)
  })

  const setDate = () => {
    const d = new Date(draft + 'T09:00:00')
    if (Number.isNaN(d.getTime())) return
    saveExamDate(d)
    setExamDate(d)
  }

  const daysLeft = examDate
    ? Math.max(
        0,
        Math.ceil((examDate.getTime() - Date.now()) / 86400000),
      )
    : null

  if (!examDate) {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← на дашборд
          </button>
        </div>
        <div className="screen-body narrow centered">
          <div className="trophy">📅</div>
          <h1 className="screen-title">Когда экзамен?</h1>
          <p className="screen-subtitle">
            Финишная прямая включается за 14 дней до даты. Укажи реальную дату —
            если ещё не записался, поставь предполагаемую: всё равно стоит
            готовиться по календарю.
          </p>
          <label className="field" style={{ maxWidth: 320, margin: '0 auto' }}>
            <span>Дата экзамена</span>
            <input
              type="date"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          </label>
          <div className="actions-row" style={{ marginTop: 18 }}>
            <button className="pill pill-primary big" onClick={setDate}>
              Включить Final Stretch →
            </button>
          </div>
        </div>
      </div>
    )
  }

  const showReadyBlock = daysLeft != null && daysLeft <= 2

  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← на дашборд
        </button>
      </div>
      <div className="screen-body narrow">
        <div className="trophy">🏁</div>
        <h1 className="screen-title">Финишная прямая</h1>
        <p className="screen-subtitle">
          До экзамена осталось <strong>{daysLeft}</strong>{' '}
          {daysLeft === 1 ? 'день' : daysLeft && daysLeft < 5 ? 'дня' : 'дней'}.
          Без новой теории, без новых тем — только закрепление того, что уже
          умеешь.
        </p>

        {showReadyBlock ? (
          <section className="outcome-section ready-zen">
            <div className="ready-emoji">🌿</div>
            <h2 className="section-title" style={{ textAlign: 'center' }}>
              Вы готовы. Отдохните.
            </h2>
            <p className="muted" style={{ textAlign: 'center' }}>
              Метрики временно скрыты — последние сутки лучше не «передрилливать».
              Если очень тревожно, прочитайте одну-две статьи в режиме «Только
              главное» и поспите.
            </p>
            <div className="actions-row" style={{ justifyContent: 'center' }}>
              <button className="pill pill-primary big" onClick={onRealExam}>
                К материалам экзамена →
              </button>
            </div>
          </section>
        ) : (
          <>
            <section className="outcome-section">
              <h2 className="section-title">Только повторение слабых мест</h2>
              <div className="fs-card">
                <div className="fs-card-emoji">🔁</div>
                <div className="fs-card-body">
                  <div className="fs-card-title">3 главы под фокусом</div>
                  <div className="fs-card-sub">
                    Все вопросы практики берутся только из тем с mastery &lt; 80%.
                    Новые темы не вводятся — стабилизируем то, что уже знаешь.
                  </div>
                </div>
              </div>
            </section>

            <section className="outcome-section">
              <h2 className="section-title">Flashcard-дрилл по формулам</h2>
              <div className="fs-card">
                <div className="fs-card-emoji">🃏</div>
                <div className="fs-card-body">
                  <div className="fs-card-title">5 минут в день</div>
                  <div className="fs-card-sub">
                    Карточки с формулами, ставками, нормативами — авто-собрано
                    из твоих ошибок. SR-интервалы 1д → 2д → 4д.
                  </div>
                </div>
              </div>
            </section>

            <section className="outcome-section">
              <h2 className="section-title">Мини-симуляция раз в 2 дня</h2>
              <div className="fs-card">
                <div className="fs-card-emoji">⏱️</div>
                <div className="fs-card-body">
                  <div className="fs-card-title">20 вопросов, 30 минут</div>
                  <div className="fs-card-sub">
                    Короткий пробный в условиях, близких к экзаменационным.
                    Помогает выдержать ритм и не выгореть на полном варианте.
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        <div className="actions-row" style={{ marginTop: 18 }}>
          {!showReadyBlock && (
            <button className="pill" onClick={onReady}>
              Показать «Вы готовы» (демо)
            </button>
          )}
          <button className="pill pill-ghost" onClick={onRealExam}>
            Материалы экзамена →
          </button>
        </div>
      </div>
    </div>
  )
}
