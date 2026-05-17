import type { Health } from '../types'

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
        бэкенд недоступен
      </span>
    )
  }
  if (!health) return <span className="badge badge-muted">проверка…</span>
  const ok = health.status === 'ok'
  const main = health.exams?.[0]
  const tooltip = [
    `graph=${health.graph_loaded}`,
    `vectors=${health.vector_store_ready}`,
    `llm=${health.llm_configured}`,
    main
      ? `${main.tasks} tasks · ${main.concepts} concepts · ${main.task_concept_links} task↔concept`
      : '',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <span className={`badge ${ok ? 'badge-ok' : 'badge-warn'}`} title={tooltip}>
      <span className="dot" />
      {ok ? 'ok' : 'degraded'}
      {main && (
        <>
          {' '}· {main.tasks} задач · {main.concepts} концептов · {main.task_concept_links}{' '}
          связей
          {main.prereq_edges ? <> · {main.prereq_edges} prereq</> : null}
        </>
      )}
    </span>
  )
}
