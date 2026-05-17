import { useEffect, useRef, useState } from 'react'
import QuestionCard from '../components/QuestionCard'
import { buildIndex, loadBank, sampleEntrance } from '../state/bank'
import type {
  BankAnswer,
  BankEntranceResult,
  BankTask,
  ExamBank,
  UserState,
} from '../types'

const TARGET = 25

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'asking'
      bank: ExamBank
      tasks: BankTask[]
      index: number
      answers: BankAnswer[]
    }
  | { kind: 'submitting' }

export default function EntranceTestScreen({
  user,
  onDone,
  onBack,
  onSkip,
}: {
  user: UserState
  onDone: (summary: BankEntranceResult) => void
  onBack: () => void
  onSkip?: () => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  const [showSkipModal, setShowSkipModal] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    ;(async () => {
      try {
        const bank = await loadBank()
        const idx = buildIndex(bank)
        const tasks = sampleEntrance(idx, TARGET)
        if (tasks.length === 0) {
          setPhase({ kind: 'error', message: 'Не удалось собрать пул вопросов.' })
          return
        }
        setPhase({ kind: 'asking', bank, tasks, index: 0, answers: [] })
      } catch (e) {
        setPhase({
          kind: 'error',
          message: e instanceof Error ? e.message : String(e),
        })
      }
    })()
  }, [])

  const handleAnswer = (outcome: {
    picked_label: string
    correct_label: string
    is_correct: boolean
  }) => {
    if (phase.kind !== 'asking') return
    const task = phase.tasks[phase.index]
    const idx = buildIndex(phase.bank)
    const theme = idx.themesByCode.get(task.theme_code)
    const chapter = theme ? idx.chaptersById.get(theme.chapter_id) : undefined
    const answer: BankAnswer = {
      task_id: task.id,
      chapter_id: chapter?.id ?? 0,
      chapter_name: chapter?.name ?? 'Без раздела',
      theme_code: task.theme_code,
      theme_name: theme?.name ?? task.theme_code,
      picked_label: outcome.picked_label,
      correct_label: outcome.correct_label,
      is_correct: outcome.is_correct,
    }
    const answers = phase.answers.concat(answer)
    const next = phase.index + 1

    if (next >= phase.tasks.length) {
      setPhase({ kind: 'submitting' })
      // Build summary locally — no slow LLM call.
      const correct = answers.filter((a) => a.is_correct).length
      const per_chapter: BankEntranceResult['per_chapter'] = {}
      for (const a of answers) {
        const key = String(a.chapter_id)
        const slot = (per_chapter[key] ??= {
          chapter_id: a.chapter_id,
          chapter_name: a.chapter_name,
          asked: 0,
          wrong: 0,
        })
        slot.asked += 1
        if (!a.is_correct) slot.wrong += 1
      }
      const summary: BankEntranceResult = {
        user_id: user.id,
        total: answers.length,
        correct,
        incorrect: answers.length - correct,
        per_chapter,
        answers,
        taken_at: new Date().toISOString(),
      }
      // tiny defer to let the UI paint "submitting"
      setTimeout(() => onDone(summary), 50)
      return
    }
    setPhase({ ...phase, index: next, answers })
  }

  const skipButton = onSkip ? (
    <button className="link-button" onClick={() => setShowSkipModal(true)}>
      пропустить →
    </button>
  ) : null

  const skipModal = showSkipModal && onSkip ? (
    <div className="modal-overlay" onClick={() => setShowSkipModal(false)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>⚠️</div>
        <h2>Пропустить входной тест?</h2>
        <p style={{ color: 'var(--fg-2)', lineHeight: 1.6, marginTop: 8 }}>
          Без входного тренажёр не знает твою стартовую базу — рекомендации
          будут начинаться «с нуля», прогноз балла станет точным только после
          25-30 ответов в обычных занятиях.
        </p>
        <ul style={{ color: 'var(--fg-2)', lineHeight: 1.8, fontSize: 13, marginTop: 8 }}>
          <li>Сейчас 25 вопросов = ~5 минут</li>
          <li>Покрывает все 13 разделов курса</li>
          <li>Сразу даст карту слабых мест</li>
        </ul>
        <div className="actions-row" style={{ marginTop: 18 }}>
          <button className="pill pill-primary" onClick={() => setShowSkipModal(false)}>
            Остаюсь, пройду тест
          </button>
          <button className="pill" onClick={onSkip}>
            Всё равно пропустить
          </button>
        </div>
      </div>
    </div>
  ) : null

  if (phase.kind === 'loading') {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← назад
          </button>
          {skipButton}
        </div>
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Готовим вопросы</h1>
          <div className="progress indeterminate">
            <div className="progress-bar" />
          </div>
          <p className="meta">Загружаем банк вопросов базового экзамена ФСФР.</p>
        </div>
        {skipModal}
      </div>
    )
  }

  if (phase.kind === 'error') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Не удалось загрузить тест</h1>
          <div className="error">{phase.message}</div>
          <button className="pill pill-primary" onClick={onBack}>
            ← назад
          </button>
        </div>
      </div>
    )
  }

  if (phase.kind === 'submitting') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Считаем результаты…</h1>
          <div className="progress indeterminate">
            <div className="progress-bar" />
          </div>
        </div>
      </div>
    )
  }

  const task = phase.tasks[phase.index]
  const idx = buildIndex(phase.bank)
  const theme = idx.themesByCode.get(task.theme_code)
  const chapter = theme ? idx.chaptersById.get(theme.chapter_id) : undefined

  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← выйти
        </button>
        <div className="meta">
          Входное тестирование · {phase.tasks.length} вопросов
        </div>
        {skipButton}
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
          chapterName={chapter?.name}
          themeName={theme?.name}
          showInstantFeedback={false}
          onAnswer={handleAnswer}
        />
      </div>
      {skipModal}
    </div>
  )
}
