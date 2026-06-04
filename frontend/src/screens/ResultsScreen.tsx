import Button from '../components/ui/Button'
import type { BankEntranceResult } from '../types'

/**
 * Итог входного теста — редакторская карточка: крупный счёт с правилом и
 * прогресс-баром, нумерованный список слабых тем, одна CTA. Острые углы,
 * хайрлайн-разделители — единый язык FinUplift.
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

  const weak = Object.values(result.per_chapter)
    .filter((c) => c.wrong > 0)
    .sort((a, b) => b.wrong / b.asked - a.wrong / a.asked)
    .slice(0, 3)

  const tone =
    pct >= 70
      ? 'Сильный старт. Закроем оставшиеся пробелы.'
      : pct >= 40
      ? 'Хорошая база — дальше прицельно по слабым темам.'
      : 'Отличная отправная точка. Начнём с фундамента.'

  return (
    <div className="screen results-screen">
      <div className="screen-body centered">
        <div className="rt-card">
          <div className="rt-eyebrow">Входной тест пройден</div>
          <h1 className="rt-headline">Ваш стартовый уровень</h1>
          <div className="rt-tone">{tone}</div>

          <div className="rt-score">
            <div className="rt-score-pct">{pct}%</div>
            <div className="rt-score-rule" />
            <div className="rt-score-side">
              <div className="rt-score-frac">
                {result.correct} <span>/ {result.total} верно</span>
              </div>
              <div className="rt-bar">
                <div className="rt-bar-fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
          </div>

          {weak.length > 0 && (
            <>
              <div className="rt-divider" />
              <div className="rt-weak-title">С этих тем начнём</div>
              {weak.map((w, i) => {
                const ok = w.asked - w.wrong
                return (
                  <div key={w.chapter_id} className="rt-weak-row">
                    <span className="rt-weak-rank">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="rt-weak-name">{w.chapter_name}</span>
                    <span className="rt-weak-score">
                      {ok} из {w.asked}
                    </span>
                  </div>
                )
              })}
            </>
          )}

          <div className="rt-cta">
            <Button size="big" full onClick={onContinue}>
              Начать подготовку →
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
