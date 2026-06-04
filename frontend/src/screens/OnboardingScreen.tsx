import { useState } from 'react'
import Logo from '../components/Logo'
import Icon, { type IconName } from '../components/ui/Icon'

/**
 * Короткий онбординг (3 шага) после регистрации — мягкий вход перед входным
 * тестом. Без сбора данных: только знакомство с продуктом и как он работает.
 */
const STEPS: { icon: IconName; title: string; text: string }[] = [
  {
    icon: 'target',
    title: 'Добро пожаловать в FinUplift',
    text: 'Адаптивный тренажёр для подготовки к экзамену ФСФР. Доведём до проходного балла по твоим слабым темам.',
  },
  {
    icon: 'layers',
    title: 'Как это работает',
    text: 'Короткий входной тест покажет пробелы. Дальше — занятия: сжатая теория под конкретные задания, потом практика с разбором ошибок.',
  },
  {
    icon: 'check',
    title: 'Учим то, что нужно',
    text: 'Алгоритм сам выбирает темы с наибольшими пробелами и отслеживает прогресс. Начнём с короткого теста — это займёт пару минут.',
  },
]

export default function OnboardingScreen({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0)
  const last = step === STEPS.length - 1
  const s = STEPS[step]

  return (
    <div className="screen">
      <div className="screen-body centered">
        <div className="onb-card">
          <div className="onb-logo">
            <Logo size={48} />
          </div>
          <div className="onb-icon" aria-hidden="true">
            <Icon name={s.icon} size={26} />
          </div>
          <h1 className="screen-title" style={{ textAlign: 'center' }}>
            {s.title}
          </h1>
          <p className="screen-subtitle" style={{ textAlign: 'center' }}>
            {s.text}
          </p>

          <div className="onb-dots" role="tablist" aria-label="Шаги">
            {STEPS.map((_, i) => (
              <span key={i} className={`onb-dot ${i === step ? 'active' : ''}`} />
            ))}
          </div>

          <div className="actions-row" style={{ marginTop: 18 }}>
            {!last ? (
              <>
                <button className="pill pill-ghost" onClick={onDone}>
                  Пропустить
                </button>
                <button
                  className="pill pill-primary big"
                  onClick={() => setStep((x) => x + 1)}
                >
                  Далее →
                </button>
              </>
            ) : (
              <button className="pill pill-primary big" onClick={onDone}>
                Пройти входной тест →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
