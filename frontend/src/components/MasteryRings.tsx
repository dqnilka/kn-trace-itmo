import { useEffect, useState } from 'react'

/**
 * Минималистичная Duolingo-like анимация после занятия.
 *
 * На каждую пройденную тему — кольцо, которое одновременно с остальными
 * доезжает от прежнего уровня знания (`from`) к новому (`to`). Затем большое
 * общее кольцо плавно меняется — растёт или падает.
 *
 * Чистый SVG + анимация через requestAnimationFrame по `stroke-dashoffset`.
 * Никаких зависимостей.
 */

export type RingDatum = {
  label: string
  from: number // 0..1 — уровень до занятия
  to: number // 0..1 — уровень после
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

function useAnimatedValue(target: number, duration: number, delay: number): number {
  const [v, setV] = useState(0)
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
      setV(easeOutCubic(p) * target)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, delay])
  return v
}

function Ring({
  datum,
  size,
  stroke,
  delay,
  showDelta,
}: {
  datum: RingDatum
  size: number
  stroke: number
  delay: number
  showDelta?: boolean
}) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  // Анимируем «прирост» от from к to: само кольцо едет к `to`, а дельту
  // подсвечиваем цветом.
  const animated = useAnimatedValue(datum.to, 900, delay)
  const pct = Math.round(animated * 100)
  const delta = Math.round((datum.to - datum.from) * 100)
  const up = datum.to >= datum.from
  const color = up ? 'var(--ring-up, #2fbf71)' : 'var(--ring-down, #e0654f)'
  const dash = circ * (1 - animated)
  return (
    <div className="mr-ring" style={{ width: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.10)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={dash}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          className="mr-ring-pct"
          fontSize={size * 0.24}
          fill="currentColor"
        >
          {pct}%
        </text>
      </svg>
      {showDelta && delta !== 0 && (
        <div className="mr-delta" style={{ color }}>
          {delta > 0 ? `+${delta}` : delta}
        </div>
      )}
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
            <Ring datum={d} size={84} stroke={9} delay={i * 120} showDelta />
            <div className="mr-theme-label" title={d.label}>
              {d.label}
            </div>
          </div>
        ))}
      </div>
      <div className="mr-overall">
        <Ring
          datum={overall}
          size={150}
          stroke={14}
          delay={themes.length * 120 + 250}
          showDelta
        />
        <div className="mr-overall-label">Общий уровень знаний</div>
      </div>
    </div>
  )
}
