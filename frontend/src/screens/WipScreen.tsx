import type { WipReason } from '../types'

const CONTENT: Record<
  WipReason,
  { emoji: string; title: string; bullets: string[] }
> = {
  theory: {
    emoji: '📚',
    title: 'Раздел «Теория»',
    bullets: [
      '13 глав базового экзамена ФСФР',
      'Статьи 800–1500 слов с подсветкой ключевых терминов',
      'Всплывающие определения и переходы к концептам графа',
      'Мини-тест после каждой главы (5–10 вопросов)',
    ],
  },
  other: {
    emoji: '🚧',
    title: 'В разработке',
    bullets: ['Эта часть приложения скоро появится.'],
  },
}

export default function WipScreen({
  reason,
  onBack,
}: {
  reason: WipReason
  onBack: () => void
}) {
  const c = CONTENT[reason]
  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← назад
        </button>
      </div>
      <div className="screen-body narrow centered">
        <div className="wip-emoji">{c.emoji}</div>
        <h1 className="screen-title">{c.title}</h1>
        <p className="screen-subtitle">в разработке</p>
        <ul className="wip-list">
          {c.bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
        <button className="pill pill-primary" onClick={onBack}>
          ← вернуться
        </button>
      </div>
    </div>
  )
}
