import { useEffect, useMemo, useState } from 'react'
import QuestionCard from '../components/QuestionCard'
import { buildIndex, loadBank } from '../state/bank'
import {
  bumpMastery,
  loadMastery,
  pickWeakThemes,
  saveMastery,
} from '../state/mastery'
import type { BankChapter, BankTask, BankTheme } from '../types'

const THEMES_PER_SESSION = 5
const QUESTIONS_PER_THEME = 3

type PlannedItem = {
  task: BankTask
  theme: BankTheme
  chapter: BankChapter | null
}

type AnswerLog = { theme_code: string; is_correct: boolean }

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'asking'
      plan: PlannedItem[]
      index: number
      answers: AnswerLog[]
    }
  | {
      kind: 'done'
      plan: PlannedItem[]
      answers: AnswerLog[]
    }

function shuffle<T>(arr: T[]): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

export default function AdaptiveSessionScreen({
  onBack,
  onRestart,
}: {
  onBack: () => void
  onRestart: () => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const b = await loadBank()
        if (cancelled) return
        const idx = buildIndex(b)
        const sizes = new Map<string, number>()
        for (const [k, v] of idx.tasksByTheme.entries()) sizes.set(k, v.length)
        const mastery = loadMastery()
        const themes = pickWeakThemes(mastery, b, THEMES_PER_SESSION, sizes)
        if (themes.length === 0) {
          setPhase({ kind: 'error', message: 'В банке нет тем с вопросами.' })
          return
        }
        const plan: PlannedItem[] = []
        for (const t of themes) {
          const pool = idx.tasksByTheme.get(t.code) ?? []
          const sample = shuffle(pool).slice(0, QUESTIONS_PER_THEME)
          const chapter = idx.chaptersById.get(t.chapter_id) ?? null
          for (const task of sample) plan.push({ task, theme: t, chapter })
        }
        if (plan.length === 0) {
          setPhase({ kind: 'error', message: 'Не удалось собрать вопросы.' })
          return
        }
        setPhase({ kind: 'asking', plan, index: 0, answers: [] })
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

  // Distinct theme boundaries (for the progress dots)
  const themeBoundaries = useMemo(() => {
    if (phase.kind !== 'asking' && phase.kind !== 'done') return []
    const plan = phase.plan
    const out: { theme: BankTheme; start: number; end: number }[] = []
    let i = 0
    while (i < plan.length) {
      const t = plan[i].theme
      let j = i
      while (j < plan.length && plan[j].theme.id === t.id) j += 1
      out.push({ theme: t, start: i, end: j - 1 })
      i = j
    }
    return out
  }, [phase])

  const onAnswer = (outcome: { is_correct: boolean }) => {
    if (phase.kind !== 'asking') return
    const cur = phase.plan[phase.index]
    saveMastery(bumpMastery(loadMastery(), cur.theme.code, outcome.is_correct))
    const answers = phase.answers.concat({
      theme_code: cur.theme.code,
      is_correct: outcome.is_correct,
    })
    const next = phase.index + 1
    if (next >= phase.plan.length) {
      setPhase({ kind: 'done', plan: phase.plan, answers })
      return
    }
    setPhase({ ...phase, index: next, answers })
  }

  if (phase.kind === 'loading') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Подбираем траекторию…</h1>
          <p className="screen-subtitle">
            Анализируем твои слабые темы и собираем 15 вопросов.
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
          <h1 className="screen-title">Не удалось запустить</h1>
          <div className="error">{phase.message}</div>
          <button className="pill pill-primary" onClick={onBack}>
            ← на главную
          </button>
        </div>
      </div>
    )
  }

  if (phase.kind === 'done') {
    const correct = phase.answers.filter((a) => a.is_correct).length
    const total = phase.answers.length
    const pct = total === 0 ? 0 : Math.round((correct / total) * 100)
    // per-theme breakdown for this session
    const sessionByTheme = new Map<
      string,
      { theme: BankTheme; asked: number; correct: number }
    >()
    for (const b of themeBoundaries) {
      sessionByTheme.set(b.theme.code, { theme: b.theme, asked: 0, correct: 0 })
    }
    for (const a of phase.answers) {
      const slot = sessionByTheme.get(a.theme_code)
      if (!slot) continue
      slot.asked += 1
      if (a.is_correct) slot.correct += 1
    }
    const rows = Array.from(sessionByTheme.values())
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <div className="trophy">🎯</div>
          <h1 className="screen-title">Сессия завершена</h1>
          <p className="screen-subtitle">
            Прошли {rows.length} тем · {total} вопросов
          </p>
          <div className="score-card big">
            <div className="ring-value-xl">{pct}%</div>
            <div className="score-card-meta">
              {correct} из {total} верно
            </div>
          </div>
          <div className="adaptive-themes">
            {rows.map((r) => {
              const p = r.asked === 0 ? 0 : r.correct / r.asked
              const cls =
                p >= 0.66 ? 'strong' : p >= 0.34 ? 'medium' : 'weak'
              return (
                <div key={r.theme.id} className={`adaptive-theme-row ${cls}`}>
                  <div className="adaptive-theme-name">{r.theme.name}</div>
                  <div className="adaptive-theme-pct">
                    {r.correct}/{r.asked} ·{' '}
                    <strong>{Math.round(p * 100)}%</strong>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="actions-row">
            <button className="pill pill-primary" onClick={onRestart}>
              Ещё одна сессия →
            </button>
            <button className="pill pill-ghost" onClick={onBack}>
              На главную
            </button>
          </div>
        </div>
      </div>
    )
  }

  const cur = phase.plan[phase.index]
  const themeIdx = themeBoundaries.findIndex(
    (b) => phase.index >= b.start && phase.index <= b.end,
  )
  const currentTheme = themeBoundaries[themeIdx]
  const correct = phase.answers.filter((a) => a.is_correct).length
  const wrong = phase.answers.length - correct

  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← прервать
        </button>
        <div className="meta">
          Адаптивная сессия · ✓ {correct} · ✗ {wrong}
        </div>
      </div>
      <div className="screen-body narrow">
        <div className="adaptive-progress">
          {themeBoundaries.map((b, i) => (
            <div
              key={b.theme.id}
              className={`adaptive-pip ${i < themeIdx ? 'done' : i === themeIdx ? 'active' : ''}`}
              title={b.theme.name}
            />
          ))}
        </div>
        <div className="adaptive-theme-head">
          Тема {themeIdx + 1} из {themeBoundaries.length} ·{' '}
          <strong>{currentTheme?.theme.name}</strong>
        </div>
        <div className="progress slim">
          <div
            className="progress-bar"
            style={{
              width: `${((phase.index + 1) / phase.plan.length) * 100}%`,
            }}
          />
        </div>
        <QuestionCard
          key={cur.task.id}
          task={cur.task}
          index={phase.index}
          total={phase.plan.length}
          chapterName={cur.chapter?.name}
          themeName={cur.theme.name}
          showInstantFeedback
          onAnswer={onAnswer}
        />
      </div>
    </div>
  )
}
