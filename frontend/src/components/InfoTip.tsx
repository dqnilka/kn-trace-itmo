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
}: {
  text: string
  size?: 'sm' | 'md'
  align?: 'left' | 'right' | 'center'
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const ref = useRef<HTMLButtonElement | null>(null)

  const place = () => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos({ top: r.top, left: r.left + r.width / 2 })
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
        className={`info-tip-icon info-tip-${size}`}
        aria-label="Подсказка"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        ⓘ
      </button>
      {open &&
        pos &&
        createPortal(
          <span
            className="info-tip-popover-fixed"
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
