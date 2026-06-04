import type { BankEntranceResult } from '../types'

/**
 * Минимальный экран «спасибо за входной» — после теста пользователь сразу
 * идёт в тренажёр. Никаких параллельных предиктов и heatmap-ов: эти данные
 * уже считаются BKT-моделью на дашборде, а здесь только короткая сводка и
 * CTA, как просил продакт.
 */
export default function ResultsScreen({
  result,
  onContinue,
}: {
  result: BankEntranceResult
  onContinue: () => void
}) {
  const pct =
    result.total === 0 ? 0 : Math.round((result.correct / result.total) * 100)

  // Топ-3 слабых раздела как полезная подсказка перед заходом в тренажёр —
  // компактным списком, без отдельных колец-предиктов.
  const weak = Object.values(result.per_chapter)
    .filter((c) => c.wrong > 0)
    .sort((a, b) => b.wrong / b.asked - a.wrong / a.asked)
    .slice(0, 3)

  return (
    <div className="screen results-screen">
      <div className="screen-body narrow centered">
        <div className="results-icon">✅</div>
        <h1 className="screen-title">Входной тест пройден</h1>
        <p className="screen-subtitle">
          Спасибо! Ответы записаны — система знает, с чего начинать обучение.
        </p>

        <div className="results-summary">
          <div className="results-summary-num">
            {result.correct}<span className="results-summary-tot">/{result.total}</span>
          </div>
          <div className="results-summary-meta">верных ответов ({pct}%)</div>
        </div>

        {weak.length > 0 && (
          <div className="results-weak">
            <div className="results-weak-title">Слабее всего:</div>
            <ul>
              {weak.map((w) => (
                <li key={w.chapter_id}>
                  <span className="dot dot-err" /> {w.chapter_name}{' '}
                  <span className="muted">
                    · {w.wrong}/{w.asked} ошибок
                  </span>
                </li>
              ))}
            </ul>
            <p className="muted small">
              Алгоритм начнёт занятие именно с них.
            </p>
          </div>
        )}

        <div className="actions-row" style={{ marginTop: 24 }}>
          <button className="pill pill-primary big" onClick={onContinue}>
            Перейти в тренажёр →
          </button>
        </div>
      </div>
    </div>
  )
}
