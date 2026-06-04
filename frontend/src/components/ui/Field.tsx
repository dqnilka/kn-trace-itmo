import { useState, type InputHTMLAttributes } from 'react'

/**
 * Поле ввода дизайн-системы: лейбл сверху, острые углы, заметный фокус,
 * для type="password" — переключатель «показать/скрыть», текст ошибки.
 */
export default function Field({
  label,
  error,
  type = 'text',
  className = '',
  ...rest
}: {
  label?: string
  error?: string | null
} & InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false)
  const isPw = type === 'password'
  const effectiveType = isPw && show ? 'text' : type
  return (
    <label className="field">
      {label && <span className="field-label">{label}</span>}
      <span className="field-wrap">
        <input
          className={`field-input ${error ? 'has-error' : ''} ${className}`}
          type={effectiveType}
          {...rest}
        />
        {isPw && (
          <button
            type="button"
            className="field-eye"
            onClick={() => setShow((s) => !s)}
            tabIndex={-1}
            aria-label={show ? 'Скрыть пароль' : 'Показать пароль'}
          >
            {show ? 'скрыть' : 'показать'}
          </button>
        )}
      </span>
      {error && <span className="field-error">{error}</span>}
    </label>
  )
}
