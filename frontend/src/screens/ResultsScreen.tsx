import Button from '../components/ui/Button'
import ProgressRing from '../components/ui/ProgressRing'
import type { BankEntranceResult } from '../types'

function knowledgeLevel(result: BankEntranceResult): number {
  if (result.total === 0) return 0
  return Math.max(0, Math.min(100, Math.round((result.correct / result.total) * 100)))
}

function encouragement(level: number): string {
  if (level >= 75) return 'Сильный старт. Дальше закроем оставшиеся пробелы.'
  if (level >= 45) return 'Хорошая база. Теперь соберём её в устойчивый результат.'
  return 'Отличная отправная точка. Начнём с фундамента и быстро соберём опору.'
}

export default function ResultsScreen({
  result,
  onContinue,
}: {
  result: BankEntranceResult
  onContinue: () => void
}) {
  const level = knowledgeLevel(result)

  return (
    <div className="screen results-screen">
      <div className="screen-body centered">
        <div className="rt-card">
          <div className="rt-eyebrow">Входной тест пройден</div>
          <div className="rt-ring-wrap" aria-label={`Стартовый уровень знаний ${level}`}>
            <ProgressRing
              value={level / 100}
              tone={level >= 75 ? 'ok' : level >= 45 ? 'warn' : 'accent'}
              size={156}
              stroke={12}
              label={String(level)}
              className="rt-level-ring"
              title={`Стартовый уровень знаний ${level}`}
            />
          </div>
          <h1 className="rt-headline">Стартовый уровень знаний</h1>
          <p className="rt-tone">{encouragement(level)}</p>
          <div className="rt-cta">
            <Button size="big" full onClick={onContinue}>
              Перейти к занятиям →
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
