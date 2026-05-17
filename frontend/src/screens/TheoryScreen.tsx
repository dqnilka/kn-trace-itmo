import { useEffect, useMemo, useState } from 'react'
import SafeMarkdown from '../components/SafeMarkdown'
import { api, isAbortError } from '../api'
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
 * «← к темам» возвращает на дашборд.
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
  const [tldr, setTldr] = useState<boolean>(false) // узел t6a: «Только главное» toggle
  const [hoverTerm, setHoverTerm] = useState<ThemeConcept | null>(null) // узлы t7/t8

  useEffect(() => {
    const ctrl = new AbortController()
    setData(null)
    setErr(null)
    setShowRaw(false)
    api
      .examTheme(ACTIVE_EXAM_SLUG, themeCode, { signal: ctrl.signal })
      .then((r) => {
        if (!ctrl.signal.aborted) setData(r)
      })
      .catch((e) => {
        if (ctrl.signal.aborted || isAbortError(e)) return
        setErr(e instanceof Error ? e.message : String(e))
      })
    return () => {
      ctrl.abort()
    }
  }, [themeCode])

  const mastery = useMemo(() => themeScore(loadMastery(), themeCode), [themeCode, data])

  // ВАЖНО: все useMemo держим ДО early-return'ов (Rules of Hooks).
  // Раньше conceptByTerm и tldrText висели после `if (!data) return` —
  // первый рендер (data=null) их не вызывал, второй (data set) вызывал,
  // → React: «Rendered more hooks than during the previous render».
  const hasSummary = !!data?.summary_md?.trim()
  const conceptsWithDef = useMemo(
    () => data?.concepts.filter((c) => c.definition.trim().length > 0) ?? [],
    [data],
  )

  /**
   * Парсим **bold** в summary как кликабельные термы — на ховере показываем
   * краткое определение из списка концептов темы (узлы t7/t8 диаграммы).
   * Это очень дешёвая эвристика: если **жирный** термин совпадает с одним из
   * терм-концептов (без регистра), выделяем его.
   */
  const conceptByTerm = useMemo(() => {
    const m = new Map<string, ThemeConcept>()
    for (const c of conceptsWithDef) {
      m.set(c.term.toLowerCase().trim(), c)
    }
    return m
  }, [conceptsWithDef])

  const tldrText = useMemo(() => {
    if (!hasSummary || !data?.summary_md) return ''
    // первый абзац + первый bullet — обычно ~200 слов
    const md = data.summary_md.trim()
    const firstPara = md.split(/\n\s*\n/)[0] ?? ''
    return firstPara.length < 800 ? md.split(/\n\s*\n/).slice(0, 2).join('\n\n') : firstPara
  }, [data?.summary_md, hasSummary])

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
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Готовим теорию…</h1>
          <div className="theory-loading">
            <span className="theory-loading-dot" />
            <span className="theory-loading-dot" />
            <span className="theory-loading-dot" />
            <span className="meta">AI собирает выжимку из учебника. ~5 секунд при первом обращении.</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="screen theory-screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← к темам
        </button>
        <div className="meta">
          📖 Теория · {data.chapter_num ? `Глава ${data.chapter_num}` : 'Раздел'}
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
            <div className="theory-article-meta">
              {data.task_count > 0 && (
                <span className="chip chip-soft">{data.task_count} задач в банке</span>
              )}
              {data.concepts.length > 0 && (
                <span className="chip chip-soft">{data.concepts.length} понятий</span>
              )}
              {mastery.confidence === 'ok' && mastery.pct != null && (
                <span
                  className={`chip ${mastery.pct >= 0.75 ? 'chip-ok' : 'chip-muted'}`}
                >
                  твой уровень — {Math.round(mastery.pct * 100)}%
                </span>
              )}
            </div>
          </header>

          {hasSummary ? (
            <>
              <div className="theory-toggle-row">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={tldr}
                    onChange={(e) => setTldr(e.target.checked)}
                  />
                  <span>Только главное</span>
                  <span className="toggle-meta">
                    {tldr ? '~200 слов' : 'полная статья'}
                  </span>
                </label>
              </div>
              <section className="theory-summary">
                <SafeMarkdown
                  components={{
                    strong: ({ children, ...rest }) => {
                      const txt = String(children ?? '').toLowerCase().trim()
                      const concept = conceptByTerm.get(txt)
                      if (!concept) return <strong {...rest}>{children}</strong>
                      return (
                        <strong
                          {...rest}
                          className="theory-term"
                          onMouseEnter={() => setHoverTerm(concept)}
                          onMouseLeave={() =>
                            setHoverTerm((cur) =>
                              cur?.id === concept.id ? null : cur,
                            )
                          }
                        >
                          {children}
                        </strong>
                      )
                    },
                  }}
                >
                  {tldr ? tldrText : data.summary_md!}
                </SafeMarkdown>
                {hoverTerm && (
                  <div className="theory-term-popup">
                    <div className="theory-term-popup-head">
                      <strong>{hoverTerm.term}</strong>
                    </div>
                    <div className="theory-term-popup-body">
                      {hoverTerm.definition.slice(0, 320)}
                      {hoverTerm.definition.length > 320 ? '…' : ''}
                    </div>
                  </div>
                )}
              </section>
            </>
          ) : (
            <section className="theory-empty">
              <p className="muted">
                В учебнике мало материала по этой теме. Перейди сразу к практике —
                на ошибках AI разберёт каждый вариант.
              </p>
            </section>
          )}

          {conceptsWithDef.length > 0 && (
            <section className="theory-concepts">
              <h2 className="theory-section-title">Понятия темы</h2>
              <div className="concept-grid">
                {conceptsWithDef.slice(0, 12).map((c) => (
                  <ConceptCard
                    key={c.id}
                    concept={c}
                    open={!!openConcepts[c.id]}
                    onToggle={() =>
                      setOpenConcepts((p) => ({ ...p, [c.id]: !p[c.id] }))
                    }
                  />
                ))}
              </div>
              {conceptsWithDef.length > 12 && (
                <p className="muted small">
                  И ещё {conceptsWithDef.length - 12} понятий — встретишь их в задачах.
                </p>
              )}
            </section>
          )}

          {data.sections.length > 0 && (
            <details
              className="theory-raw-sections"
              open={showRaw}
              onToggle={(e) => setShowRaw((e.target as HTMLDetailsElement).open)}
            >
              <summary>
                📄 Показать оригинальные фрагменты учебника ({data.sections.length})
              </summary>
              <div className="theory-raw-body">
                {data.sections.map((s, i) => (
                  <section key={i} className="theory-raw-section">
                    <div className="theory-raw-path">{s.section_path}</div>
                    <div className="theory-raw-text">
                      <SafeMarkdown>
                        {(s.excerpt || s.snippet).slice(0, 2000)}
                      </SafeMarkdown>
                    </div>
                  </section>
                ))}
              </div>
            </details>
          )}
        </article>

        <div className="theory-cta">
          <div className="theory-cta-body">
            <div className="theory-cta-title">Проверить на тесте?</div>
            <div className="theory-cta-meta">
              Мини-сессия 5-10 вопросов · {data.task_count} задач в банке темы
            </div>
          </div>
          <button
            className="pill pill-primary big"
            onClick={() => onPractice(themeCode)}
            disabled={data.task_count === 0}
          >
            Проверить на тесте →
          </button>
        </div>
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
          📚 {concept.prereq_count} prereq{concept.prereq_count === 1 ? '' : 's'}
        </div>
      )}
    </div>
  )
}
