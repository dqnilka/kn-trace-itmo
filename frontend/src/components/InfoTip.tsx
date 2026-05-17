import { useEffect, useRef, useState } from 'react'

/**
 * Lightweight tooltip: shows a styled popover on hover (desktop) or tap
 * (mobile/touch). Plain HTML ``title`` is unreliable visually — this gives
 * us a consistent look and lets the text wrap to multiple lines.
 */
export default function InfoTip({
  text,
  size = 'sm',
  align = 'right',
}: {
  text: string
  size?: 'sm' | 'md'
  align?: 'left' | 'right' | 'center'
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)

  // Close popover on outside click (covers touch where mouseleave doesn't fire).
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [open])

  return (
    <span
      ref={ref}
      className="info-tip-wrap"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className={`info-tip-icon info-tip-${size}`}
        aria-label="Подсказка"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        ⓘ
      </button>
      {open && <span className={`info-tip-popover align-${align}`}>{text}</span>}
    </span>
  )
}
