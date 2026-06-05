import { useEffect, useState } from 'react'

/**
 * Кольцо прогресса с анимацией заполнения (0 → value при монтировании).
 * Цвет — через tone. Используется в дашборде/результатах/ките.
 */
export default function ProgressRing({
  value,
  size = 64,
  stroke = 7,
  tone = 'accent',
  label,
}: {
  value: number // 0..1
  size?: number
  stroke?: number
  tone?: 'accent' | 'ok' | 'warn' | 'err' | 'ink' | 'neutral'
  label?: string
}) {
  const [v, setV] = useState(0)
  useEffect(() => {
    let raf = 0
    let start: number | null = null
    const dur = 900
    const tick = (ts: number) => {
      if (start === null) start = ts
      const p = Math.min(1, (ts - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setV(eased * value)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])

  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const color = `var(--${tone === 'ink' ? 'fg' : tone === 'neutral' ? 'fg-3' : tone})`
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="pring">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--bg-3)" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - v)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={size * 0.3}
        fontWeight="700"
        fill="var(--fg)"
      >
        {label ?? `${Math.round(v * 100)}`}
      </text>
    </svg>
  )
}
