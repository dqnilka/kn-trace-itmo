import Logo from '../components/Logo'
import Icon, { type IconName } from '../components/ui/Icon'
import Button from '../components/ui/Button'

/**
 * Приветственный экран после регистрации — один содержательный шаг:
 * ценностный заголовок + три понятных пункта «как это работает» + CTA на
 * входной тест. Без пустоты и лишних иконок.
 */
const POINTS: { icon: IconName; title: string; text: string }[] = [
  {
    icon: 'target',
    title: 'Входной тест за 5 минут',
    text: 'Покрывает все 13 разделов и сразу показывает, где у тебя пробелы.',
  },
  {
    icon: 'theory',
    title: 'Теория под конкретные задания',
    text: 'Короткий разбор именно того, что спрашивают в задачах темы.',
  },
  {
    icon: 'practice',
    title: 'Практика и прогресс',
    text: 'Решаешь, видишь разбор ошибок и рост уровня по каждой теме.',
  },
]

export default function OnboardingScreen({ onDone }: { onDone: () => void }) {
  return (
    <div className="screen">
      <div className="screen-body centered">
        <div className="welcome-card">
          <div className="welcome-brand">
            <Logo size={34} />
            <span className="welcome-brand-name">FinUplift</span>
          </div>

          <div className="welcome-eyebrow">Подготовка к экзамену ФСФР</div>
          <h1 className="welcome-title">
            Учим только то, где у тебя пробелы — до проходного балла
          </h1>

          <div className="welcome-points">
            {POINTS.map((p) => (
              <div key={p.title} className="welcome-point">
                <span className="welcome-point-icon">
                  <Icon name={p.icon} size={20} />
                </span>
                <div>
                  <div className="welcome-point-title">{p.title}</div>
                  <div className="welcome-point-text">{p.text}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="welcome-actions">
            <Button size="big" full onClick={onDone}>
              Пройти входной тест →
            </Button>
            <button className="link-button welcome-skip" onClick={onDone}>
              Пропустить пока
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
