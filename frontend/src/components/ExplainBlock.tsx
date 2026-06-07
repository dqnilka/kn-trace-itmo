import { useEffect, useState } from 'react'
import SafeMarkdown from './SafeMarkdown'
import Icon from './ui/Icon'
import { api } from '../api'
import { ACTIVE_EXAM_SLUG } from '../state/bank'
import type { ExplainResponse } from '../types'

/**
 * Lazily fetches the LLM explanation for a single bank task and renders the
 * markdown. Used after a wrong answer in adaptive and practice modes.
 */
export default function ExplainBlock({
  taskId,
  pickedLabel,
  autoFetch = true,
}: {
  taskId: number
  pickedLabel: string | null
  autoFetch?: boolean
}) {
  const [data, setData] = useState<ExplainResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!autoFetch) return
    let cancelled = false
    setLoading(true)
    setErr(null)
    setData(null)
    api
      .explain(ACTIVE_EXAM_SLUG, taskId, pickedLabel)
      .then((r) => {
        if (!cancelled) setData(r)
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [taskId, pickedLabel, autoFetch])

  if (loading) {
    return (
      <div className="explain-block">
        <div className="explain-head">
          <span className="explain-icon"><Icon name="idea" size={16} /></span>
          <span className="explain-title">Готовим разбор…</span>
        </div>
        <div className="progress indeterminate">
          <div className="progress-bar" />
        </div>
        <p className="meta">Подбираем объяснение по учебнику. Обычно до 10 секунд.</p>
      </div>
    )
  }

  if (err) {
    return <div className="error">Разбор недоступен: {err}</div>
  }

  if (!data) return null

  return (
    <div className="explain-block">
      <div className="explain-head">
        <span className="explain-icon"><Icon name="idea" size={16} /></span>
        <span className="explain-title">Разбор задачи</span>
      </div>
      <div className="theory feedback-theory">
        <SafeMarkdown>
          {data.explanation_md}
        </SafeMarkdown>
      </div>
    </div>
  )
}
