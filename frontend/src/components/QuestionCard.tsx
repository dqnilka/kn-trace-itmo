import { useEffect, useState } from 'react'
import ExplainBlock from './ExplainBlock'
import { api } from '../api'
import { ACTIVE_EXAM_SLUG } from '../state/bank'
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

/**
 * Считаем число неверных ответов по теме за текущую сессию.
 * Хранится в sessionStorage, чтобы переживать переходы между PracticeScreen и
 * другими экранами, но обнуляться между сессиями браузера.
 */
const REPEAT_KEY = 'akt:sessionMistakes'

function readMistakes(): Record<string, number> {
  try {
    const raw = sessionStorage.getItem(REPEAT_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeMistakes(m: Record<string, number>): void {
  try {
    sessionStorage.setItem(REPEAT_KEY, JSON.stringify(m))
  } catch {
    // ignore
  }
}

export function bumpThemeMistake(themeCode: string): number {
  const m = readMistakes()
  m[themeCode] = (m[themeCode] ?? 0) + 1
  writeMistakes(m)
  return m[themeCode]
}

export default function QuestionCard({
  task,
  index,
  total,
  chapterName,
  themeName,
  themeCode,
  showInstantFeedback,
  enableExplain = true,
  onAnswer,
  onOpenTheory,
}: {
  task: BankTask
  index: number
  total: number
  chapterName?: string
  themeName?: string
  themeCode?: string
  showInstantFeedback?: boolean
  enableExplain?: boolean
  onAnswer: (outcome: AnswerOutcome) => void
  /**
   * Узлы c4/w7 диаграммы: «ссылка на теорию: Глава X, раздел Y». Если задан,
   * показываем кнопку «📖 К теме в справочнике» после раскрытия ответа.
   */
  onOpenTheory?: (themeCode: string) => void
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [wantExplain, setWantExplain] = useState(false)
  const [flashcardSaved, setFlashcardSaved] = useState(false)
  const [showMiniCard, setShowMiniCard] = useState(false)
  const [miniCardSeconds, setMiniCardSeconds] = useState(45)
  const correctOption = task.options.find((o) => o.is_correct)
  const correctLabel = correctOption?.label ?? ''

  useEffect(() => {
    setPicked(null)
    setRevealed(false)
    setSubmitted(false)
    setWantExplain(false)
    setFlashcardSaved(false)
    setShowMiniCard(false)
    setMiniCardSeconds(45)
  }, [task.id])

  // Обратный отсчёт для мини-карточки повторения (узел w9 диаграммы).
  useEffect(() => {
    if (!showMiniCard) return
    if (miniCardSeconds <= 0) return
    const id = setTimeout(() => setMiniCardSeconds((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [showMiniCard, miniCardSeconds])

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
      if (!isCorrect) {
        // авто-flashcard для повторения (узел w6)
        setFlashcardSaved(true)
        // проверим, повторная ли ошибка по теме (узел w8 → w9)
        const mistakes = bumpThemeMistake(task.theme_code)
        if (mistakes >= 2) setShowMiniCard(true)
        if (enableExplain) setWantExplain(true)
      } else if (enableExplain) {
        // Узлы c2-c3 диаграммы: на верном ответе тоже доступен AI-разбор,
        // только не автоматически — чтобы не сжигать токены на «и так понятно».
        // Пользователь кликает «🧠 AI-разбор» по желанию.
      }
    } else {
      if (submitted) return
      setSubmitted(true)
      onAnswer({ picked_label: picked, correct_label: correctLabel, is_correct: isCorrect })
    }
  }

  const proceed = () => {
    if (!picked || submitted) return
    setSubmitted(true)
    onAnswer({
      picked_label: picked,
      correct_label: correctLabel,
      is_correct: picked === correctLabel,
    })
  }

  const optionClass = (label: string) => {
    if (!revealed) return picked === label ? 'option picked' : 'option'
    if (label === correctLabel) return 'option correct'
    if (picked === label && label !== correctLabel) return 'option wrong'
    return 'option dimmed'
  }

  return (
    <article className="qcard">
      <header className="qcard-head">
        <div className="qcard-progress">
          вопрос {index + 1} из {total}
          {task.task_number ? ` · ${task.task_number}` : ''}
        </div>
        <div className="qcard-meta">
          {chapterName && <span className="chip chip-soft">{chapterName}</span>}
          {themeName && <span className="chip chip-muted">{themeName}</span>}
          {task.difficulty != null && (
            <span className={`chip chip-diff diff-${task.difficulty}`}>
              {task.difficulty === 1 ? 'легко' : 'средне'}
            </span>
          )}
        </div>
      </header>

      <div className="qcard-body">
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
            {/* AI-разбор: на неверном фетчится автоматически, на верном — по клику (c2). */}
            {enableExplain && !wantExplain && (
              <button className="pill pill-ghost" onClick={() => setWantExplain(true)}>
                🧠 AI-разбор
              </button>
            )}
            {/* Узлы c4/w7: ссылка на теорию (если задан колбэк). */}
            {onOpenTheory && themeCode && (
              <button
                className="pill pill-ghost"
                onClick={() => onOpenTheory(themeCode)}
                title={themeName ? `Открыть тему «${themeName}»` : 'Открыть тему в справочнике'}
              >
                📖 К теме в справочнике
              </button>
            )}
            <button className="pill pill-primary" onClick={proceed}>
              Дальше →
            </button>
          </>
        )}
      </footer>

      {revealed && flashcardSaved && picked !== correctLabel && (
        <div className="flashcard-chip" title="Эта задача добавлена в колоду повторения">
          🃏 Карточка для повторения создана
        </div>
      )}

      {showMiniCard && (
        <div className="mini-theory-card">
          <div className="mini-theory-head">
            <span className="mini-theory-emoji">📖</span>
            <span className="mini-theory-title">
              Повторная ошибка по теме «{themeName ?? task.theme_code}»
            </span>
            <span className="mini-theory-timer">
              {miniCardSeconds > 0 ? `${miniCardSeconds} c` : 'готово'}
            </span>
          </div>
          <p className="mini-theory-body">
            Прежде чем идти дальше — короткое напоминание. Перечитай ключевое
            определение из контекста, иначе следующая задача снова уйдёт в
            ошибку. Полный разбор и связи — в карточке темы.
          </p>
          <div className="mini-theory-actions">
            <a
              className="link-button"
              href={`#theme-${task.theme_code}`}
              onClick={(e) => e.preventDefault()}
            >
              открыть статью в справочнике →
            </a>
            <button
              className="pill pill-ghost"
              onClick={() => setShowMiniCard(false)}
            >
              понятно, продолжить
            </button>
          </div>
        </div>
      )}

      {wantExplain && picked && (
        <ExplainBlock taskId={task.id} pickedLabel={picked} />
      )}
    </article>
  )
}
