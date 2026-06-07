import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/**
 * Подсказка-popover. Раньше всплывашка обрезалась родительским overflow/стек-
 * контекстом (карточки глав на Главной) — иногда не появлялась. Теперь popover
 * рендерится порталом в body с position: fixed по координатам иконки —
 * клиппинг исключён.
 */
export default function InfoTip({
  text,
  size = 'sm',
  label = 'i',
  className = '',
}: {
  text: string
  size?: 'sm' | 'md'
  align?: 'left' | 'right' | 'center'
  label?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number; side: 'top' | 'bottom' } | null>(null)
  const ref = useRef<HTMLButtonElement | null>(null)

  const place = () => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const width = 240
    const margin = 14
    const left = Math.min(
      window.innerWidth - width / 2 - margin,
      Math.max(width / 2 + margin, r.left + r.width / 2),
    )
    setPos({
      top: r.top > 96 ? r.top : r.bottom,
      left,
      side: r.top > 96 ? 'top' : 'bottom',
    })
  }

  useLayoutEffect(() => {
    if (open) place()
  }, [open])

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
      window.removeEventListener('mousedown', onDown)
    }
  }, [open])

  return (
    <>
      <button
        ref={ref}
        type="button"
        className={`info-tip-icon info-tip-${size} ${className}`}
        aria-label="Подробнее"
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        {label}
      </button>
      {open &&
        pos &&
        createPortal(
          <span
            className={`info-tip-popover-fixed is-${pos.side}`}
            style={{ top: pos.top, left: pos.left }}
            role="tooltip"
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  )
}
