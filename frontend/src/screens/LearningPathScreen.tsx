import { useEffect, useMemo, useRef, useState } from 'react'
import SafeMarkdown from '../components/SafeMarkdown'
import { api } from '../api'
import QuestionCard from '../components/QuestionCard'
import MasteryRings, { type RingDatum } from '../components/MasteryRings'
import { ACTIVE_EXAM_SLUG, buildIndex, loadBank } from '../state/bank'
import {
  bumpMastery,
  loadMastery,
  overallStats,
  pickWeakThemes,
  saveMastery,
  themeScore,
} from '../state/mastery'
import type {
  BankChapter,
  BankTask,
  BankTheme,
  ExamBank,
  MasteryStore,
} from '../types'

/**
 * Адаптивное занятие в стиле Duolingo/Brilliant:
 *   1. Берём 3 темы по приоритету слабости (через pickWeakThemes).
 *   2. Для каждой темы — короткая теория из учебника (GET /theme/{code}),
 *      затем 2-3 практических задачи.
 *   3. На неверном ответе показывается AI-разбор (через QuestionCard).
 *   4. В конце — сводка прогресса по сессии (без BKT-мистики, простой «N/M
 *      верно по теме»).
 */

const SESSION_THEMES = 3
const TASKS_PER_THEME = 3

type ThemeUnit = {
  theme: BankTheme
  chapter: BankChapter | null
  tasks: BankTask[]
}

type TheoryContent = {
  summary_md: string | null
  sections: { section_path: string; excerpt: string }[]
}

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'theory'
      units: ThemeUnit[]
      idx: number
      content: TheoryContent | null
      theoryError: string | null
    }
  | {
      kind: 'practice'
      units: ThemeUnit[]
      idx: number
      taskIdx: number
      sessionAnswers: { theme_code: string; is_correct: boolean }[]
    }
  | {
      kind: 'done'
      units: ThemeUnit[]
      answers: { theme_code: string; is_correct: boolean }[]
    }

function shuffle<T>(arr: T[]): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

export default function LearningPathScreen({
  onBack,
  onRestart,
}: {
  onBack: () => void
  onRestart: () => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  // Snapshot of mastery BEFORE the session — used to animate the rings
  // (before% → after%) on the completion screen.
  const prevMasteryRef = useRef<MasteryStore>({})

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const bank = await loadBank()
        if (cancelled) return
        const idx = buildIndex(bank)
        const sizes = new Map<string, number>()
        for (const [k, v] of idx.tasksByTheme.entries()) sizes.set(k, v.length)
        const mastery = loadMastery()
        prevMasteryRef.current = mastery
        const themes = pickWeakThemes(mastery, bank, SESSION_THEMES, sizes)
        if (themes.length === 0) {
          setPhase({ kind: 'error', message: 'В банке нет тем с вопросами.' })
          return
        }
        const units: ThemeUnit[] = themes.map((t) => {
          const pool = idx.tasksByTheme.get(t.code) ?? []
          return {
            theme: t,
            chapter: idx.chaptersById.get(t.chapter_id) ?? null,
            tasks: shuffle(pool).slice(0, TASKS_PER_THEME),
          }
        })
        setPhase({
          kind: 'theory',
          units,
          idx: 0,
          content: null,
          theoryError: null,
        })
      } catch (e) {
        setPhase({
          kind: 'error',
          message: e instanceof Error ? e.message : String(e),
        })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Whenever theory phase begins for a new unit, fetch the LLM-clean summary.
  useEffect(() => {
    if (phase.kind !== 'theory') return
    if (phase.content !== null || phase.theoryError !== null) return
    const unit = phase.units[phase.idx]
    if (!unit) return
    let cancelled = false
    api
      .examTheme(
        ACTIVE_EXAM_SLUG,
        unit.theme.code,
        unit.tasks.map((t) => t.id),
      )
      .then((r) => {
        if (cancelled) return
        const sections = (r.sections || []).slice(0, 2).map((s) => ({
          section_path: s.section_path,
          excerpt: s.excerpt || s.snippet,
        }))
        const summary = (r.summary_md || '').trim()
        const content: TheoryContent = {
          summary_md: summary || null,
          sections,
        }
        const empty = !summary && sections.length === 0
        setPhase((p) =>
          p.kind === 'theory'
            ? { ...p, content: empty ? null : content, theoryError: empty ? 'empty' : null }
            : p,
        )
      })
      .catch((e) => {
        if (!cancelled) {
          setPhase((p) =>
            p.kind === 'theory'
              ? { ...p, theoryError: e instanceof Error ? e.message : String(e) }
              : p,
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [phase])

  const progress = useMemo(() => {
    if (phase.kind === 'loading' || phase.kind === 'error') return 0
    if (phase.kind === 'done') return 1
    const total = phase.units.length
    const unitProgress = phase.kind === 'theory' ? 0 : (phase.taskIdx + 1) / (TASKS_PER_THEME + 1)
    return (phase.idx + (phase.kind === 'theory' ? 0 : unitProgress)) / total
  }, [phase])

  const goPractice = () => {
    if (phase.kind !== 'theory') return
    setPhase({
      kind: 'practice',
      units: phase.units,
      idx: phase.idx,
      taskIdx: 0,
      sessionAnswers: [],
    })
  }

  const onAnswer = (outcome: {
    picked_label: string
    correct_label: string
    is_correct: boolean
  }) => {
    if (phase.kind !== 'practice') return
    const unit = phase.units[phase.idx]
    const next = {
      theme_code: unit.theme.code,
      is_correct: outcome.is_correct,
    }
    // local mastery + persist
    saveMastery(bumpMastery(loadMastery(), unit.theme.code, outcome.is_correct))
    const answers = phase.sessionAnswers.concat(next)
    const nextTaskIdx = phase.taskIdx + 1
    if (nextTaskIdx >= unit.tasks.length) {
      // unit done, go to next theme's theory OR session summary
      const nextUnitIdx = phase.idx + 1
      if (nextUnitIdx >= phase.units.length) {
        setPhase({ kind: 'done', units: phase.units, answers })
        return
      }
      setPhase({
        kind: 'theory',
        units: phase.units,
        idx: nextUnitIdx,
        content: null,
        theoryError: null,
      })
      return
    }
    setPhase({ ...phase, taskIdx: nextTaskIdx, sessionAnswers: answers })
  }

  if (phase.kind === 'loading') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Подбираем путь обучения…</h1>
          <p className="screen-subtitle">
            Беру 3 темы, где у тебя сейчас самые большие пробелы, и собираю
            теорию + 3 задачи на каждую.
          </p>
          <div className="progress indeterminate">
            <div className="progress-bar" />
          </div>
        </div>
      </div>
    )
  }

  if (phase.kind === 'error') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Не удалось запустить занятие</h1>
          <div className="error">{phase.message}</div>
          <button className="pill pill-primary" onClick={onBack}>
            ← на главную
          </button>
        </div>
      </div>
    )
  }

  if (phase.kind === 'done') {
    const total = phase.answers.length
    const correct = phase.answers.filter((a) => a.is_correct).length
    const prev = prevMasteryRef.current
    const now = loadMastery()

    const pctOf = (store: MasteryStore, code: string): number =>
      themeScore(store, code).pct ?? 0

    const themeRings: RingDatum[] = phase.units.map((u) => ({
      label: u.theme.name,
      from: pctOf(prev, u.theme.code),
      to: pctOf(now, u.theme.code),
    }))
    const overall: RingDatum = {
      label: 'Общий уровень',
      from: overallStats(prev).pct ?? 0,
      to: overallStats(now).pct ?? 0,
    }

    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Занятие завершено</h1>
          <p className="screen-subtitle">
            Прошли {phase.units.length} тем · {correct} из {total} верно
          </p>

          <MasteryRings themes={themeRings} overall={overall} />

          <div className="actions-row" style={{ marginTop: 24 }}>
            <button className="pill pill-primary" onClick={onRestart}>
              Ещё одно занятие →
            </button>
            <button className="pill pill-ghost" onClick={onBack}>
              На главную
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (phase.kind === 'theory') {
    const unit = phase.units[phase.idx]
    const content = phase.content
    const loading = content === null && !phase.theoryError
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← прервать
          </button>
          <div className="meta">
            Шаг {phase.idx + 1} из {phase.units.length} · теория
          </div>
        </div>
        <div className="screen-body narrow">
          <PathProgress units={phase.units} curIdx={phase.idx} curStep="theory" />
          <article className="learn-card learn-theory">
            <header className="learn-head">
              <div className="learn-eyebrow">
                {unit.chapter ? `${unit.chapter.name} · ` : ''}Тема {unit.theme.code}
              </div>
              <h2 className="learn-title">{unit.theme.name}</h2>
            </header>
            <div className="learn-body">
              {loading && (
                <div className="theory-loading">
                  <span className="theory-loading-dot" />
                  <span className="theory-loading-dot" />
                  <span className="theory-loading-dot" />
                  <span className="meta">
                    Готовим объяснение темы по учебнику… ~5 сек
                  </span>
                </div>
              )}
              {phase.theoryError === 'empty' && (
                <div className="muted">
                  Теории по этой теме в учебнике мало. Переходим сразу к
                  практике — на ошибках разберём каждый вариант.
                </div>
              )}
              {phase.theoryError && phase.theoryError !== 'empty' && (
                <div className="error">{phase.theoryError}</div>
              )}
              {content?.summary_md && (
                <div className="theory summary-theory">
                  <SafeMarkdown>
                    {content.summary_md}
                  </SafeMarkdown>
                </div>
              )}
              {content && !content.summary_md && content.sections.length > 0 && (
                <details className="theory-raw">
                  <summary>Показать сырой фрагмент из учебника</summary>
                  {content.sections.map((s, i) => (
                    <section key={i} className="learn-section">
                      <div className="learn-section-path">{s.section_path}</div>
                      <div className="learn-section-body theory">
                        <SafeMarkdown>
                          {s.excerpt.slice(0, 1200)}
                        </SafeMarkdown>
                      </div>
                    </section>
                  ))}
                </details>
              )}
            </div>
            <footer className="learn-footer">
              <div className="learn-note">
                Дальше — {unit.tasks.length} задач(и) на эту тему.
              </div>
              <button className="pill pill-primary" onClick={goPractice} disabled={loading}>
                Перейти к практике →
              </button>
            </footer>
          </article>
        </div>
      </div>
    )
  }

  // practice
  const unit = phase.units[phase.idx]
  const task = unit.tasks[phase.taskIdx]
  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← прервать
        </button>
        <div className="meta">
          Шаг {phase.idx + 1} из {phase.units.length} · задача{' '}
          {phase.taskIdx + 1} из {unit.tasks.length}
        </div>
      </div>
      <div className="screen-body narrow">
        <PathProgress units={phase.units} curIdx={phase.idx} curStep="practice" />
        <div className="learn-eyebrow learn-context">
          Сейчас: <strong>{unit.theme.name}</strong>
        </div>
        <QuestionCard
          key={task.id}
          task={task}
          index={phase.taskIdx}
          total={unit.tasks.length}
          chapterName={unit.chapter?.name}
          themeName={unit.theme.name}
          showInstantFeedback
          onAnswer={onAnswer}
        />
      </div>
    </div>
  )
}

function PathProgress({
  units,
  curIdx,
  curStep,
}: {
  units: ThemeUnit[]
  curIdx: number
  curStep: 'theory' | 'practice'
}) {
  return (
    <ol className="path-progress">
      {units.map((u, i) => {
        const status =
          i < curIdx ? 'done' : i === curIdx ? 'active' : 'pending'
        return (
          <li key={u.theme.id} className={`path-step ${status}`}>
            <span className="path-step-circle">{i + 1}</span>
            <div className="path-step-meta">
              <div className="path-step-name">{u.theme.name}</div>
              {i === curIdx && (
                <div className="path-step-sub">
                  {curStep === 'theory' ? '📖 теория' : '✏ практика'}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
