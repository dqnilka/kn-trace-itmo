import { useEffect, useMemo, useState } from 'react'
import QuestionCard from '../components/QuestionCard'
import { buildIndex, loadBank } from '../state/bank'
import { bumpMastery, loadMastery, saveMastery } from '../state/mastery'
import type {
  BankChapter,
  BankTask,
  BankTheme,
  ExamBank,
  UserState,
} from '../types'

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'asking'
      tasks: BankTask[]
      index: number
      correct: number
      wrong: number
      answers: boolean[]
      theme: BankTheme
      chapter: BankChapter | null
    }
  | {
      kind: 'done'
      correct: number
      wrong: number
      total: number
      theme: BankTheme
      chapter: BankChapter | null
      answers: boolean[] // sequence of correctness for ps2 mini-heatmap
    }

const SESSION_SIZE = 10

function shuffle<T>(arr: T[]): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

export default function PracticeScreen({
  themeCode,
  onBack,
  onPickAnotherTheme,
  onOpenTheory,
}: {
  user: UserState
  themeCode: string
  onBack: () => void
  onPickAnotherTheme: () => void
  onOpenTheory?: (code: string) => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  const [bank, setBank] = useState<ExamBank | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const b = await loadBank()
        if (cancelled) return
        setBank(b)
        const idx = buildIndex(b)
        const theme = idx.themesByCode.get(themeCode)
        if (!theme) {
          setPhase({ kind: 'error', message: 'Тема не найдена в банке.' })
          return
        }
        const chapter = idx.chaptersById.get(theme.chapter_id) ?? null
        const pool = idx.tasksByTheme.get(themeCode) ?? []
        if (pool.length === 0) {
          setPhase({ kind: 'error', message: 'В этой теме нет вопросов.' })
          return
        }
        setPhase({
          kind: 'asking',
          tasks: shuffle(pool).slice(0, SESSION_SIZE),
          index: 0,
          correct: 0,
          wrong: 0,
          answers: [],
          theme,
          chapter,
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
  }, [themeCode])

  const restart = useMemo(
    () => () => {
      if (!bank) return
      const idx = buildIndex(bank)
      const theme = idx.themesByCode.get(themeCode)
      if (!theme) return
      const chapter = idx.chaptersById.get(theme.chapter_id) ?? null
      const pool = idx.tasksByTheme.get(themeCode) ?? []
      setPhase({
        kind: 'asking',
        tasks: shuffle(pool).slice(0, SESSION_SIZE),
        index: 0,
        correct: 0,
        wrong: 0,
        answers: [],
        theme,
        chapter,
      })
    },
    [bank, themeCode],
  )

  const onAnswer = (outcome: { is_correct: boolean }) => {
    if (phase.kind !== 'asking') return
    saveMastery(bumpMastery(loadMastery(), phase.theme.code, outcome.is_correct))
    const nextCorrect = phase.correct + (outcome.is_correct ? 1 : 0)
    const nextWrong = phase.wrong + (outcome.is_correct ? 0 : 1)
    const nextAnswers = phase.answers.concat(outcome.is_correct)
    const idx = phase.index + 1
    if (idx >= phase.tasks.length) {
      setPhase({
        kind: 'done',
        correct: nextCorrect,
        wrong: nextWrong,
        total: phase.tasks.length,
        theme: phase.theme,
        chapter: phase.chapter,
        answers: nextAnswers,
      })
      return
    }
    setPhase({
      ...phase,
      index: idx,
      correct: nextCorrect,
      wrong: nextWrong,
      answers: nextAnswers,
    })
  }

  if (phase.kind === 'loading') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Готовим вопросы…</h1>
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
          <h1 className="screen-title">Не удалось открыть тему</h1>
          <div className="error">{phase.message}</div>
          <button className="pill pill-primary" onClick={onPickAnotherTheme}>
            ← к выбору темы
          </button>
        </div>
      </div>
    )
  }

  if (phase.kind === 'done') {
    const pct =
      phase.total === 0 ? 0 : Math.round((phase.correct / phase.total) * 100)
    // Узел ps3 диаграммы: «3+ ошибки в сессии → рекомендация по главе».
    const recommendChapter = phase.wrong >= 3 && phase.chapter
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <div className="trophy">🎯</div>
          <h1 className="screen-title">Сессия завершена</h1>
          <p className="screen-subtitle">
            {phase.chapter?.name} · {phase.theme.name}
          </p>
          <div className="score-card big">
            <div className="ring-value-xl">{pct}%</div>
            <div className="score-card-meta">
              {phase.correct} из {phase.total} верно
            </div>
          </div>

          {/* ps2: «обновлённый heatmap» — последовательность ответов в сессии */}
          <div className="session-heatmap" title="Хронология ответов">
            {phase.answers.map((ok, i) => (
              <div
                key={i}
                className={`session-heatmap-cell ${ok ? 'ok' : 'wrong'}`}
                title={`Вопрос ${i + 1}: ${ok ? 'верно' : 'неверно'}`}
              >
                {ok ? '✓' : '✗'}
              </div>
            ))}
          </div>

          {/* ps3 → ps4: рекомендация изучить главу при 3+ ошибках */}
          {recommendChapter && (
            <div className="session-recommend">
              <div className="session-recommend-emoji">📚</div>
              <div className="session-recommend-body">
                <div className="session-recommend-title">
                  В этой сессии {phase.wrong} ошибки — рекомендуем подтянуть
                  тему перед следующей попыткой.
                </div>
                <div className="session-recommend-sub">
                  Глава {phase.chapter?.num}. {phase.chapter?.name}. Открой
                  статью в справочнике — там объяснение и связанные понятия.
                </div>
                {onOpenTheory && (
                  <button
                    className="pill pill-cta"
                    onClick={() => onOpenTheory(phase.theme.code)}
                  >
                    📖 Открыть тему в справочнике
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="actions-row">
            <button className="pill pill-primary" onClick={restart}>
              Ещё раз
            </button>
            <button className="pill" onClick={onPickAnotherTheme}>
              Сменить тему
            </button>
            <button className="pill pill-ghost" onClick={onBack}>
              На дашборд
            </button>
          </div>
        </div>
      </div>
    )
  }

  const task = phase.tasks[phase.index]
  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onPickAnotherTheme}>
          ← сменить тему
        </button>
        <div className="meta">
          {phase.chapter?.name} · {phase.theme.name} · ✓ {phase.correct} · ✗{' '}
          {phase.wrong}
        </div>
      </div>
      <div className="screen-body narrow">
        <div className="progress slim">
          <div
            className="progress-bar"
            style={{
              width: `${((phase.index + 1) / phase.tasks.length) * 100}%`,
            }}
          />
        </div>
        <QuestionCard
          key={task.id}
          task={task}
          index={phase.index}
          total={phase.tasks.length}
          chapterName={phase.chapter?.name}
          themeName={phase.theme.name}
          themeCode={phase.theme.code}
          showInstantFeedback
          onAnswer={onAnswer}
          onOpenTheory={onOpenTheory}
        />
      </div>
    </div>
  )
}
