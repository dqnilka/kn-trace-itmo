import { useEffect, useMemo, useState } from 'react'
import SafeMarkdown from '../components/SafeMarkdown'
import { TheorySkeleton } from '../components/ui/Skeleton'
import RateWidget from '../components/ui/RateWidget'
import { api } from '../api'
import { ACTIVE_EXAM_SLUG } from '../state/bank'
import { loadMastery, themeScore } from '../state/mastery'
import type { ThemeArticleResponse, ThemeConcept } from '../types'

/**
 * Полноэкранный read-mode для одной темы.
 *
 * Сначала — чистая выжимка от LLM (``summary_md``), затем — концепты темы из
 * графа (``term + definition``), затем — сворачиваемые сырые фрагменты
 * учебника как «источник истины».
 *
 * Внизу CTA «Решать задачи →» — ведёт в обычную практику по теме. Кнопка
 * «← к темам» возвращает на главную.
 */
export default function TheoryScreen({
  themeCode,
  onBack,
  onPractice,
}: {
  themeCode: string
  onBack: () => void
  onPractice: (code: string) => void
}) {
  const [data, setData] = useState<ThemeArticleResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [showRaw, setShowRaw] = useState(false)
  const [openConcepts, setOpenConcepts] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let cancelled = false
    setData(null)
    setErr(null)
    setShowRaw(false)
    api
      .examTheme(ACTIVE_EXAM_SLUG, themeCode)
      .then((r) => {
        if (!cancelled) setData(r)
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [themeCode])

  const mastery = useMemo(() => themeScore(loadMastery(), themeCode), [themeCode, data])

  if (err) {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← к темам
          </button>
        </div>
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Теория недоступна</h1>
          <div className="error">{err}</div>
          <button className="pill pill-primary" onClick={onBack}>
            Назад
          </button>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← к темам
          </button>
        </div>
        <div className="screen-body narrow">
          <div className="meta" style={{ marginBottom: 14 }}>
            Составляем разбор под задания темы — обычно несколько секунд
          </div>
          <article className="theory-article">
            <TheorySkeleton />
          </article>
        </div>
      </div>
    )
  }

  const hasSummary = !!data.summary_md?.trim()
  const conceptsWithDef = data.concepts.filter((c) => c.definition.trim().length > 0)

  return (
    <div className="screen theory-screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← к темам
        </button>
        <div className="meta">
          Теория · {data.chapter_num ? `Глава ${data.chapter_num}` : 'Раздел'}
          {data.summary_cached && (
            <span className="chip chip-muted" style={{ marginLeft: 8 }}>
              кэш
            </span>
          )}
        </div>
      </div>

      <div className="screen-body narrow">
        <article className="theory-article">
          <header className="theory-article-head">
            <div className="theory-eyebrow">
              {data.chapter_name ? `${data.chapter_name} · ` : ''}Тема {data.theme_code}
            </div>
            <h1 className="theory-article-title">{data.theme_name}</h1>
          </header>

          {hasSummary ? (
            <section className="theory-summary">
              <SafeMarkdown>
                {data.summary_md!}
              </SafeMarkdown>
            </section>
          ) : (
            <section className="theory-empty">
              <p className="muted">
                В учебнике мало материала по этой теме. Перейди сразу к практике —
                на ошибках разберём каждый вариант.
              </p>
            </section>
          )}
        </article>

        <div className="theory-cta">
          <div className="theory-cta-body">
            <div className="theory-cta-title">Готов проверить себя?</div>
            <div className="theory-cta-meta">
              {data.task_count} задач в этой теме · разберём ошибки
            </div>
          </div>
          <button
            className="pill pill-primary big"
            onClick={() => onPractice(themeCode)}
            disabled={data.task_count === 0}
          >
            Решать задачи →
          </button>
        </div>

        <RateWidget kind="theory" refId={themeCode} label="Полезна ли эта теория?" />
      </div>
    </div>
  )
}

function ConceptCard({
  concept,
  open,
  onToggle,
}: {
  concept: ThemeConcept
  open: boolean
  onToggle: () => void
}) {
  const truncated = concept.definition.length > 140 && !open
  const text = truncated ? concept.definition.slice(0, 140) + '…' : concept.definition
  return (
    <div className={`concept-grid-card ${open ? 'open' : ''}`}>
      <div className="concept-grid-term">{concept.term}</div>
      <div className="concept-grid-def">{text}</div>
      {(truncated || open) && (
        <button className="concept-grid-toggle" onClick={onToggle}>
          {open ? 'свернуть ↑' : 'раскрыть ↓'}
        </button>
      )}
      {concept.prereq_count > 0 && (
        <div className="concept-grid-prereq">
          {concept.prereq_count} prereq{concept.prereq_count === 1 ? '' : 's'}
        </div>
      )}
    </div>
  )
}
