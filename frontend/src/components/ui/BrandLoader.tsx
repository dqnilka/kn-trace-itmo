import BrandWordmark from '../BrandWordmark'

/**
 * Брендовый лоадер: пульсирующее лого + подпись. Используется на экранах
 * ожидания вместо «голой» пустоты.
 */
export default function BrandLoader({
  label = 'Загружаем…',
  hint,
}: {
  label?: string
  hint?: string
}) {
  return (
    <div className="brand-loader" role="status" aria-live="polite">
      <div className="brand-loader-mark">
        <BrandWordmark className="brand-loader-wordmark" />
        <span className="brand-loader-ring" aria-hidden="true" />
      </div>
      <div className="brand-loader-label">{label}</div>
      {hint && <div className="brand-loader-hint">{hint}</div>}
    </div>
  )
}
