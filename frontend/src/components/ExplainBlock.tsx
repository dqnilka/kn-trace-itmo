import { useEffect, useState } from 'react'
import SafeMarkdown from './SafeMarkdown'
import { api, isAbortError } from '../api'
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
    const ctrl = new AbortController()
    setLoading(true)
    setErr(null)
    setData(null)
    api
      .explain(ACTIVE_EXAM_SLUG, taskId, pickedLabel, { signal: ctrl.signal })
      .then((r) => {
        if (!ctrl.signal.aborted) setData(r)
      })
      .catch((e) => {
        // abort/timeout — это штатное размонтирование, не ошибка UI
        if (ctrl.signal.aborted || isAbortError(e)) return
        setErr(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => {
      ctrl.abort()
    }
  }, [taskId, pickedLabel, autoFetch])

  if (loading) {
    return (
      <div className="explain-block">
        <div className="explain-head">
          <span className="explain-icon">🧠</span>
          <span className="explain-title">AI готовит разбор…</span>
        </div>
        <div className="progress indeterminate">
          <div className="progress-bar" />
        </div>
        <p className="meta">RAG-поиск по учебнику + генерация объяснения. До 10 секунд.</p>
      </div>
    )
  }

  if (err) {
    return <div className="error">AI-разбор недоступен: {err}</div>
  }

  if (!data) return null

  return (
    <div className="explain-block">
      <div className="explain-head">
        <span className="explain-icon">🧠</span>
        <span className="explain-title">AI-разбор задачи</span>
        <span className="chip chip-muted">
          {data.generation_mode === 'llm' ? 'LLM' : 'extractive'}
        </span>
      </div>
      <div className="theory feedback-theory">
        <SafeMarkdown>{data.explanation_md}</SafeMarkdown>
      </div>
      {data.sources.length > 0 && (
        <details className="explain-sources">
          <summary>источники: {data.sources.length}</summary>
          <ul>
            {data.sources.map((s, i) => (
              <li key={`${s.node_id}-${i}`}>
                <code>{s.node_type}</code> {s.snippet.slice(0, 240)}
                {s.snippet.length > 240 ? '…' : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
