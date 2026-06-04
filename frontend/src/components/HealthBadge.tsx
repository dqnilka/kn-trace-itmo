import type { Health } from '../types'

/**
 * Тихий индикатор состояния бэкенда: цветная точка + короткий статус.
 * Технические цифры графа (задачи/концепты/связи/prereq) намеренно НЕ
 * показываем пользователю — это внутренняя телеметрия, не часть продукта.
 * Подробности остаются в title (tooltip) для отладки.
 */
export default function HealthBadge({
  health,
  error,
}: {
  health: Health | null
  error: string | null
}) {
  if (error) {
    return (
      <span className="badge badge-error" title={error}>
        <span className="dot" /> нет связи
      </span>
    )
  }
  if (!health)
    return (
      <span className="badge badge-muted">
        <span className="dot" /> …
      </span>
    )
  const ok = health.status === 'ok'
  const main = health.exams?.[0]
  const tooltip = [
    `graph=${health.graph_loaded}`,
    `vectors=${health.vector_store_ready}`,
    `llm=${health.llm_configured}`,
    main ? `${main.tasks} tasks · ${main.concepts} concepts` : '',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <span className={`badge ${ok ? 'badge-ok' : 'badge-warn'}`} title={tooltip}>
      <span className="dot" />
      {ok ? 'онлайн' : 'нестабильно'}
    </span>
  )
}
