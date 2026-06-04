import type { BankEntranceResult } from '../types'

/**
 * Итог входного теста: крупный результат-кольцо + слабые темы карточками с
 * понятной формулировкой и одна CTA. Мотивирующий тон вместо клинического.
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
  const circ = 2 * Math.PI * 52

  const weak = Object.values(result.per_chapter)
    .filter((c) => c.wrong > 0)
    .sort((a, b) => b.wrong / b.asked - a.wrong / a.asked)
    .slice(0, 3)

  const tone =
    pct >= 70
      ? 'Сильный старт!'
      : pct >= 40
      ? 'Хорошая база — есть куда расти.'
      : 'Отличная отправная точка.'

  return (
    <div className="screen results-screen">
      <div className="screen-body narrow centered">
        <h1 className="screen-title">Входной тест пройден</h1>
        <p className="screen-subtitle">
          {tone} Дальше — занятия по твоим слабым темам.
        </p>

        <div
          className="result-ring"
          role="img"
          aria-label={`Результат ${pct} процентов`}
        >
          <svg width="130" height="130" viewBox="0 0 130 130">
            <circle
              cx="65"
              cy="65"
              r="52"
              fill="none"
              stroke="var(--bg-3)"
              strokeWidth="12"
            />
            <circle
              cx="65"
              cy="65"
              r="52"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circ}
              strokeDashoffset={circ * (1 - pct / 100)}
              transform="rotate(-90 65 65)"
            />
            <text x="65" y="60" textAnchor="middle" className="result-ring-pct">
              {pct}%
            </text>
            <text x="65" y="84" textAnchor="middle" className="result-ring-sub">
              {result.correct}/{result.total} верно
            </text>
          </svg>
        </div>

        {weak.length > 0 && (
          <div className="result-weak">
            <div className="result-weak-title">С этих тем начнём:</div>
            {weak.map((w) => {
              const ok = w.asked - w.wrong
              return (
                <div key={w.chapter_id} className="result-weak-card">
                  <span className="result-weak-name">{w.chapter_name}</span>
                  <span className="result-weak-score">
                    {ok} из {w.asked} верно
                  </span>
                </div>
              )
            })}
          </div>
        )}

        <div className="actions-row" style={{ marginTop: 26 }}>
          <button className="pill pill-primary big" onClick={onContinue}>
            Начать подготовку →
          </button>
        </div>
      </div>
    </div>
  )
}
