import { useEffect, useState } from 'react'

/**
 * Анимация изменения уровня знаний после занятия.
 *
 * Для каждой темы (и общего уровня) показываем кольцо:
 *   • бледная «призрачная» дуга — каким уровень БЫЛ до занятия (`from`);
 *   • яркая дуга едет от `from` к `to` — видно, вырос балл или упал;
 *   • цвет: рост → зелёный, падение → красный, без изменений → нейтральный;
 *   • снизу — крупная дельта со стрелкой (▲ +12 / ▼ −5 / — без изменений).
 */

export type RingDatum = {
  label: string
  from: number // 0..1 — до занятия
  to: number // 0..1 — после
}

function useAnimatedBetween(from: number, to: number, duration: number, delay: number): number {
  const [v, setV] = useState(from)
  useEffect(() => {
    let raf = 0
    let start: number | null = null
    const tick = (ts: number) => {
      if (start === null) start = ts
      const elapsed = ts - start - delay
      if (elapsed < 0) {
        raf = requestAnimationFrame(tick)
        return
      }
      const p = Math.min(1, elapsed / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setV(from + (to - from) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    setV(from)
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [from, to, duration, delay])
  return v
}

type Dir = 'up' | 'down' | 'same'
function dirOf(from: number, to: number): Dir {
  const d = Math.round(to * 100) - Math.round(from * 100)
  return d > 0 ? 'up' : d < 0 ? 'down' : 'same'
}
const TONE: Record<Dir, string> = {
  up: 'var(--ok)',
  down: 'var(--err)',
  same: 'var(--fg-3)',
}

function Ring({
  datum,
  size,
  stroke,
  delay,
}: {
  datum: RingDatum
  size: number
  stroke: number
  delay: number
}) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const animated = useAnimatedBetween(datum.from, datum.to, 1000, delay)
  const dir = dirOf(datum.from, datum.to)
  const color = TONE[dir]
  const deltaPts = Math.round(datum.to * 100) - Math.round(datum.from * 100)
  return (
    <div className="mr-ring" style={{ width: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* трек */}
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--bg-3)" strokeWidth={stroke} />
        {/* призрак «было» */}
        {dir !== 'same' && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--border-strong)"
            strokeWidth={stroke}
            strokeLinecap="butt"
            strokeDasharray={circ}
            strokeDashoffset={circ * (1 - datum.from)}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
        {/* активная дуга — едет from→to */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - animated)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          className="mr-ring-pct"
          fontSize={size * 0.26}
        >
          {Math.round(animated * 100)}
        </text>
      </svg>
      <div className={`mr-delta mr-${dir}`}>
        {dir === 'up' && `▲ +${deltaPts}`}
        {dir === 'down' && `▼ ${deltaPts}`}
        {dir === 'same' && '— без изменений'}
      </div>
    </div>
  )
}

export default function MasteryRings({
  themes,
  overall,
}: {
  themes: RingDatum[]
  overall: RingDatum
}) {
  return (
    <div className="mastery-rings">
      <div className="mr-themes">
        {themes.map((d, i) => (
          <div key={i} className="mr-theme">
            <Ring datum={d} size={88} stroke={9} delay={i * 160} />
            <div className="mr-theme-label" title={d.label}>
              {d.label}
            </div>
          </div>
        ))}
      </div>
      <div className="mr-overall">
        <Ring datum={overall} size={156} stroke={13} delay={themes.length * 160 + 300} />
        <div className="mr-overall-label">Общий уровень знаний</div>
      </div>
    </div>
  )
}
