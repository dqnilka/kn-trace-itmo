import { useEffect, useState } from 'react'
import ExplainBlock from './ExplainBlock'
import { api } from '../api'
import { ACTIVE_EXAM_SLUG } from '../state/bank'
import { decodeUser, getToken } from '../state/auth'
import { loadUser } from '../state/user'
import type { BankTask } from '../types'

export type AnswerOutcome = {
  picked_label: string
  correct_label: string
  is_correct: boolean
}

function fireEvent(taskId: number, pickedLabel: string, isCorrect: boolean): void {
  const user = loadUser()
  if (!user) return
  // Fire-and-forget: do NOT await; never block the UI on this.
  api
    .event(ACTIVE_EXAM_SLUG, {
      user_id: user.id,
      task_id: taskId,
      picked_label: pickedLabel,
      is_correct: isCorrect,
    })
    .catch((e) => {
      // Server-side mastery is best-effort while we still keep local mastery.
      console.warn('event log failed:', e)
    })
}

export default function QuestionCard({
  task,
  index,
  total,
  chapterName,
  themeName,
  showInstantFeedback,
  enableExplain = true,
  onAnswer,
}: {
  task: BankTask
  index: number
  total: number
  chapterName?: string
  themeName?: string
  showInstantFeedback?: boolean
  enableExplain?: boolean
  onAnswer: (outcome: AnswerOutcome) => void
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [wantExplain, setWantExplain] = useState(false)
  const correctOption = task.options.find((o) => o.is_correct)
  const correctLabel = correctOption?.label ?? ''
  // Админ видит верный вариант до ответа — для проверки корректности графа.
  const isAdmin = !!decodeUser(getToken())?.is_admin

  useEffect(() => {
    setPicked(null)
    setRevealed(false)
    setWantExplain(false)
  }, [task.id])

  const handlePick = (label: string) => {
    if (revealed) return
    setPicked(label)
  }

  const handleSubmit = () => {
    if (!picked || revealed) return
    const isCorrect = picked === correctLabel
    // Server-side event: always log, even on correct answers (BKT needs both signals).
    fireEvent(task.id, picked, isCorrect)
    if (showInstantFeedback) {
      setRevealed(true)
      // Auto-fetch explain only if user got it wrong; correct answers don't need it.
      if (!isCorrect && enableExplain) {
        setWantExplain(true)
      }
    } else {
      onAnswer({ picked_label: picked, correct_label: correctLabel, is_correct: isCorrect })
    }
  }

  const proceed = () => {
    if (!picked) return
    onAnswer({
      picked_label: picked,
      correct_label: correctLabel,
      is_correct: picked === correctLabel,
    })
  }

  const optionClass = (label: string) => {
    if (!revealed) {
      const peek = isAdmin && label === correctLabel ? ' is-correct-peek' : ''
      return (picked === label ? 'option picked' : 'option') + peek
    }
    if (label === correctLabel) return 'option correct'
    if (picked === label && label !== correctLabel) return 'option wrong'
    return 'option dimmed'
  }

  return (
    <article className="qcard">
      <header className="qcard-head">
        <div className="qcard-progress">
          Вопрос {index + 1} из {total}
          {isAdmin && task.task_number ? (
            <span className="qcard-code"> · {task.task_number}</span>
          ) : null}
        </div>
        <div className="qcard-meta">
          {themeName && <span className="chip chip-muted">{themeName}</span>}
          {task.difficulty != null && (
            <span
              className={`diff-dot diff-${task.difficulty}`}
              title={task.difficulty === 1 ? 'легко' : 'средне'}
            />
          )}
        </div>
      </header>

      <div className="qcard-body">
        {isAdmin && !revealed && (
          <div className="admin-peek-badge" title="Виден только администратору">
            🔎 режим проверки · верный вариант отмечен
          </div>
        )}
        <p className="qcard-text">{task.task_text}</p>
        <ul className="options-list">
          {task.options.map((o) => (
            <li key={o.label}>
              <button
                type="button"
                className={optionClass(o.label)}
                disabled={revealed}
                onClick={() => handlePick(o.label)}
              >
                <span className="option-label">{o.label}</span>
                <span className="option-text">{o.text}</span>
                {isAdmin && !revealed && o.label === correctLabel && (
                  <span className="opt-correct-tick">✓</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <footer className="qcard-actions">
        {!revealed && (
          <button
            className="pill pill-primary"
            disabled={!picked}
            onClick={handleSubmit}
          >
            Ответить
          </button>
        )}
        {revealed && (
          <>
            <div
              className={`feedback-inline ${picked === correctLabel ? 'ok' : 'err'}`}
            >
              {picked === correctLabel ? 'Верно!' : `Правильно: ${correctLabel}`}
            </div>
            {enableExplain && picked !== correctLabel && !wantExplain && (
              <button className="pill pill-ghost" onClick={() => setWantExplain(true)}>
                🧠 AI-разбор
              </button>
            )}
            <button className="pill pill-primary" onClick={proceed}>
              Дальше →
            </button>
          </>
        )}
      </footer>

      {wantExplain && picked && (
        <ExplainBlock taskId={task.id} pickedLabel={picked} />
      )}
    </article>
  )
}
