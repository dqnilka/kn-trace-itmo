import Button from './Button'

/**
 * Подтверждение деструктивного действия (прерывание занятия, перезапуск теста).
 * Острый модал в стиле дизайн-системы.
 */
export default function ConfirmDialog({
  open,
  title,
  text,
  confirmLabel = 'Подтвердить',
  cancelLabel = 'Отмена',
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  text?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>{title}</h2>
        {text && (
          <p style={{ color: 'var(--fg-2)', lineHeight: 1.55, marginTop: 8 }}>{text}</p>
        )}
        <div className="actions-row" style={{ marginTop: 18 }}>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  )
}
