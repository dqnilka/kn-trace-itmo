import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost'

/** Кнопка дизайн-системы: острые углы, чёткие состояния, loading/full. */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingLabel,
  full = false,
  className = '',
  children,
  disabled,
  ...rest
}: {
  variant?: Variant
  size?: 'md' | 'big'
  loading?: boolean
  loadingLabel?: string
  full?: boolean
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = [
    'pill',
    variant === 'primary' && 'pill-primary',
    variant === 'ghost' && 'pill-ghost',
    size === 'big' && 'big',
    full && 'pill-full',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button className={cls} disabled={disabled || loading} {...rest}>
      {loading ? (loadingLabel ?? '…') : children}
    </button>
  )
}
