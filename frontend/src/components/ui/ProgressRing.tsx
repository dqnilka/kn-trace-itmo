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
  className = '',
  title,
}: {
  value: number | null // 0..1, null = not enough data
  size?: number
  stroke?: number
  tone?: 'accent' | 'ok' | 'warn' | 'err' | 'ink' | 'neutral'
  label?: string
  className?: string
  title?: string
}) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const target = value ?? 0
    let raf = 0
    let start: number | null = null
    const dur = 900
    const tick = (ts: number) => {
      if (start === null) start = ts
      const p = Math.min(1, (ts - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setV(eased * target)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])

  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const color = `var(--${tone === 'ink' ? 'fg' : tone === 'neutral' ? 'fg-3' : tone})`
  const text = label ?? (value == null ? '?' : `${Math.round(value * 100)}`)
  const fontSize = text.length >= 4 ? size * 0.2 : text.length >= 3 ? size * 0.24 : size * 0.3
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={`pring ${className}`.trim()}
      role="img"
      aria-label={title || text}
    >
      {title && <title>{title}</title>}
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
        fontSize={fontSize}
        fontWeight="700"
        fill="var(--fg)"
      >
        {text}
      </text>
    </svg>
  )
}
