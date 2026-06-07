import BrandWordmark from '../components/BrandWordmark'
import Icon, { type IconName } from '../components/ui/Icon'
import Button from '../components/ui/Button'

const POINTS: { icon: IconName; title: string; text: string }[] = [
  {
    icon: 'target',
    title: 'Диагностика по всем разделам',
    text: '25 вопросов показывают стартовый уровень знаний и темы, с которых лучше начать.',
  },
  {
    icon: 'layers',
    title: 'Личный маршрут подготовки',
    text: 'Занятия подбираются по пробелам: сначала фундамент, потом более точные темы.',
  },
  {
    icon: 'theory',
    title: 'Теория рядом с практикой',
    text: 'Короткие объяснения идут перед заданиями и помогают закреплять именно нужные понятия.',
  },
]

export default function OnboardingScreen({
  onStart,
  onSkip,
}: {
  onStart: () => void
  onSkip: () => void
}) {
  return (
    <div className="screen">
      <div className="screen-body centered">
        <div className="welcome-card">
          <div className="welcome-brand">
            <BrandWordmark />
          </div>

          <div className="welcome-eyebrow">Подготовка к базовому ФСФР</div>
          <h1 className="welcome-title">
            Построим личный маршрут к проходному уровню
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
            <Button size="big" full onClick={onStart}>
              Начать входной тест →
            </Button>
            <button className="link-button welcome-skip" onClick={onSkip}>
              Перейти к занятиям
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
