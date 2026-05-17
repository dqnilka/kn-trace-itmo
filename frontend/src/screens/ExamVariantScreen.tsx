import { useEffect, useMemo, useState } from 'react'
import QuestionCard from '../components/QuestionCard'
import { buildIndex, loadBank } from '../state/bank'
import { bumpMastery, loadMastery, pushVariant, saveMastery, seededSample } from '../state/mastery'
import type {
  BankChapter,
  BankTask,
  BankTheme,
  ExamBank,
  ExamVariantSummary,
} from '../types'

const EXAM_SIZE = 50
const SEED_BASE = 4242
// Узел m2: 120 минут на полный экзамен. Под наш мок-вариант на 50 вопросов
// мы используем 60 минут — этого достаточно, чтобы продемонстрировать таймер
// и предупреждения. Подставится 120 минут при полноценных 80 вопросах.
const EXAM_SECONDS = 60 * 60

type AnswerLog = {
  task_id: number
  theme_code: string
  chapter_id: number
  is_correct: boolean
}

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'intro'; tasks: BankTask[]; bank: ExamBank }
  | {
      kind: 'asking'
      tasks: BankTask[]
      bank: ExamBank
      index: number
      answers: AnswerLog[]
      startedAt: number // ms epoch
    }
  | { kind: 'timeout'; tasks: BankTask[]; bank: ExamBank; answers: AnswerLog[] }
  | {
      kind: 'done'
      tasks: BankTask[]
      bank: ExamBank
      answers: AnswerLog[]
      timedOut?: boolean
    }

function pickExamSample(bank: ExamBank, variantId: number): BankTask[] {
  // Proportional by chapter, deterministic per variantId.
  const idx = buildIndex(bank)
  const total = bank.tasks.length
  const pool: BankTask[] = []
  for (const c of bank.chapters) {
    const tasks = idx.tasksByChapter.get(c.id) ?? []
    if (tasks.length === 0) continue
    const quota = Math.max(1, Math.round((tasks.length / total) * EXAM_SIZE))
    const sample = seededSample(tasks, quota, SEED_BASE + variantId * 31 + c.id)
    pool.push(...sample)
  }
  // Final trim to EXAM_SIZE with seeded shuffle for stability
  return seededSample(pool, Math.min(EXAM_SIZE, pool.length), SEED_BASE + variantId)
}

export default function ExamVariantScreen({
  variantId,
  onBack,
  onOutcome,
}: {
  variantId: number
  onBack: () => void
  onOutcome?: (passed: boolean, pct: number) => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const b = await loadBank()
        if (cancelled) return
        const tasks = pickExamSample(b, variantId)
        if (tasks.length === 0) {
          setPhase({ kind: 'error', message: 'Не удалось собрать вариант.' })
          return
        }
        setPhase({ kind: 'intro', tasks, bank: b })
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
  }, [variantId])

  const start = () => {
    if (phase.kind !== 'intro') return
    setPhase({
      kind: 'asking',
      tasks: phase.tasks,
      bank: phase.bank,
      index: 0,
      answers: [],
      startedAt: Date.now(),
    })
  }

  // Таймер обратного отсчёта (узлы m4/m4a/m7a диаграммы).
  // Перерисовываем каждую секунду, чтобы класс предупреждения переключался.
  const [now, setNow] = useState<number>(() => Date.now())
  useEffect(() => {
    if (phase.kind !== 'asking') return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [phase.kind])

  useEffect(() => {
    if (phase.kind !== 'asking') return
    const elapsed = Math.floor((now - phase.startedAt) / 1000)
    if (elapsed >= EXAM_SECONDS) {
      setPhase({ kind: 'timeout', tasks: phase.tasks, bank: phase.bank, answers: phase.answers })
    }
  }, [now, phase])

  const finalizeAndSummarize = (
    answers: AnswerLog[],
    tasks: BankTask[],
    bank: ExamBank,
    timedOut: boolean,
  ) => {
    const idx = buildIndex(bank)
    const correct = answers.filter((a) => a.is_correct).length
    const per_chapter: ExamVariantSummary['per_chapter'] = {}
    for (const a of answers) {
      const ch = idx.chaptersById.get(a.chapter_id)
      const key = String(a.chapter_id)
      const slot = (per_chapter[key] ??= {
        chapter_id: a.chapter_id,
        chapter_name: ch?.name ?? 'Без раздела',
        asked: 0,
        wrong: 0,
      })
      slot.asked += 1
      if (!a.is_correct) slot.wrong += 1
    }
    // Не сохраняем пустые «варианты»: если пользователь нажал «завершить
    // досрочно» не ответив ни на один вопрос, в истории такая запись только
    // зашумит UI и приведёт к делению на ноль на дашборде.
    if (answers.length > 0) {
      pushVariant({
        variant_id: variantId,
        taken_at: new Date().toISOString(),
        total: answers.length,
        correct,
        per_chapter,
      })
    }
    setPhase({ kind: 'done', tasks, bank, answers, timedOut })
  }

  const onAnswer = (outcome: {
    picked_label: string
    correct_label: string
    is_correct: boolean
  }) => {
    if (phase.kind !== 'asking') return
    const task = phase.tasks[phase.index]
    const idx = buildIndex(phase.bank)
    const theme = idx.themesByCode.get(task.theme_code)
    const chapter_id = theme?.chapter_id ?? 0
    const answers = phase.answers.concat({
      task_id: task.id,
      theme_code: task.theme_code,
      chapter_id,
      is_correct: outcome.is_correct,
    })
    // Mock exam contributes to mastery too
    saveMastery(bumpMastery(loadMastery(), task.theme_code, outcome.is_correct))
    const next = phase.index + 1
    if (next >= phase.tasks.length) {
      finalizeAndSummarize(answers, phase.tasks, phase.bank, false)
      return
    }
    setPhase({ ...phase, index: next, answers })
  }

  const finishEarly = () => {
    if (phase.kind !== 'asking') return
    finalizeAndSummarize(phase.answers, phase.tasks, phase.bank, false)
  }

  const { chaptersOfTasks } = useMemo(() => {
    if (phase.kind !== 'intro' && phase.kind !== 'asking' && phase.kind !== 'done')
      return { chaptersOfTasks: new Map<number, BankChapter>() }
    const idx = buildIndex(phase.bank)
    const m = new Map<number, BankChapter>()
    for (const task of phase.tasks) {
      const theme = idx.themesByCode.get(task.theme_code)
      if (!theme) continue
      const c = idx.chaptersById.get(theme.chapter_id)
      if (c) m.set(c.id, c)
    }
    return { chaptersOfTasks: m }
  }, [phase])

  if (phase.kind === 'loading') {
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <h1 className="screen-title">Готовим вариант…</h1>
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
          <h1 className="screen-title">Не получилось</h1>
          <div className="error">{phase.message}</div>
          <button className="pill pill-primary" onClick={onBack}>
            ← назад
          </button>
        </div>
      </div>
    )
  }

  if (phase.kind === 'intro') {
    return (
      <div className="screen">
        <div className="screen-head">
          <button className="link-button" onClick={onBack}>
            ← назад
          </button>
        </div>
        <div className="screen-body narrow centered">
          <div className="trophy">📝</div>
          <h1 className="screen-title">Пробный вариант №{variantId}</h1>
          <p className="screen-subtitle">
            {phase.tasks.length} вопросов · охват {chaptersOfTasks.size} разделов
          </p>
          <ul className="exam-rules">
            <li>
              На весь вариант — {Math.floor(EXAM_SECONDS / 60)} минут (обратный
              таймер сверху).
            </li>
            <li>Подсказки отключены — отвечай как на настоящем экзамене.</li>
            <li>Можно завершить досрочно, тогда оценим по сделанному.</li>
            <li>Проходной балл — 80%.</li>
            <li>Если время выйдет — посчитаем по сделанным ответам.</li>
          </ul>
          <div className="actions-row">
            <button className="pill pill-primary big" onClick={start}>
              Начать экзамен →
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (phase.kind === 'timeout') {
    // узлы m4a → m7a → m8 диаграммы: «Время вышло» → подсчёт результата
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          <div className="trophy">⏱️</div>
          <h1 className="screen-title">Время вышло</h1>
          <p className="screen-subtitle">
            Не страшно — посчитаем по фактически сделанным ответам. На реальном
            экзамене таймер не остановишь, поэтому такой опыт — часть подготовки.
          </p>
          <div className="actions-row">
            <button
              className="pill pill-primary big"
              onClick={() =>
                finalizeAndSummarize(phase.answers, phase.tasks, phase.bank, true)
              }
            >
              Показать результат →
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (phase.kind === 'done') {
    const correct = phase.answers.filter((a) => a.is_correct).length
    const total = phase.answers.length
    const pct = total === 0 ? 0 : Math.round((correct / total) * 100)
    const passed = pct >= 80
    const idx = buildIndex(phase.bank)
    const byChapter = new Map<
      number,
      { name: string; asked: number; wrong: number }
    >()
    for (const a of phase.answers) {
      const ch = idx.chaptersById.get(a.chapter_id)
      const slot = byChapter.get(a.chapter_id) ?? {
        name: ch?.name ?? '—',
        asked: 0,
        wrong: 0,
      }
      slot.asked += 1
      if (!a.is_correct) slot.wrong += 1
      byChapter.set(a.chapter_id, slot)
    }
    const sortedChapters = Array.from(byChapter.entries()).sort(
      (a, b) => b[1].wrong / b[1].asked - a[1].wrong / a[1].asked,
    )
    return (
      <div className="screen">
        <div className="screen-body narrow centered">
          {phase.timedOut && (
            <div className="banner-warn" style={{ marginBottom: 16 }}>
              <div className="banner-emoji">⏱️</div>
              <div className="banner-body">
                Время вышло — не успели до окончания таймера. Считаем по сделанным
                ответам ({total} из {phase.tasks.length}).
              </div>
            </div>
          )}
          <div className="trophy">{passed ? '🏆' : '📚'}</div>
          <h1 className="screen-title">
            {passed ? 'Отличный результат' : 'Не совсем получилось'}
          </h1>
          <p className="screen-subtitle">
            Пробный вариант №{variantId} · {correct} из {total} верно
          </p>
          <div className="score-card big">
            <div
              className="ring-value-xl"
              style={{ color: passed ? '#16a34a' : '#ef4444' }}
            >
              {pct}%
            </div>
            <div className="score-card-meta">проходной 80%</div>
          </div>

          <h2 className="section-title">По разделам</h2>
          <div className="exam-chapter-list">
            {sortedChapters.map(([id, s]) => {
              const r = s.wrong / s.asked
              const cls =
                r === 0
                  ? 'strong'
                  : r < 0.34
                    ? 'strong'
                    : r < 0.67
                      ? 'medium'
                      : 'weak'
              return (
                <div key={id} className={`exam-chapter-row ${cls}`}>
                  <span>{s.name}</span>
                  <span className="muted">
                    {s.asked - s.wrong}/{s.asked}
                  </span>
                </div>
              )
            })}
          </div>

          <div className="actions-row">
            {onOutcome ? (
              <button
                className="pill pill-primary big"
                onClick={() => onOutcome(passed, pct)}
              >
                {passed ? 'Что дальше →' : 'Разобрать ошибки →'}
              </button>
            ) : (
              <button className="pill pill-primary" onClick={onBack}>
                На дашборд →
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  const cur = phase.tasks[phase.index]
  const idx = buildIndex(phase.bank)
  const theme = idx.themesByCode.get(cur.theme_code)
  const chapter = theme ? idx.chaptersById.get(theme.chapter_id) : undefined
  const correct = phase.answers.filter((a) => a.is_correct).length

  const elapsedSec = Math.floor((now - phase.startedAt) / 1000)
  const remainingSec = Math.max(0, EXAM_SECONDS - elapsedSec)
  const remainingMin = Math.floor(remainingSec / 60)
  const timerClass =
    remainingSec < 60
      ? 'timer-flash'
      : remainingSec < 5 * 60
        ? 'timer-pulse'
        : remainingSec < 10 * 60
          ? 'timer-warn'
          : 'timer-ok'
  const mm = Math.floor(remainingSec / 60)
    .toString()
    .padStart(2, '0')
  const ss = (remainingSec % 60).toString().padStart(2, '0')

  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={finishEarly}>
          завершить досрочно
        </button>
        <div className={`mock-timer ${timerClass}`} title="Обратный отсчёт">
          ⏱ {mm}:{ss}
          {remainingMin < 10 && remainingMin >= 5 && (
            <span className="timer-hint">меньше 10 мин</span>
          )}
          {remainingMin < 5 && remainingSec >= 60 && (
            <span className="timer-hint">меньше 5 мин!</span>
          )}
          {remainingSec < 60 && (
            <span className="timer-hint">меньше минуты!</span>
          )}
        </div>
        <div className="meta">
          Пробный №{variantId} · {phase.index + 1}/{phase.tasks.length} ·{' '}
          ✓ {correct}
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
          key={cur.id}
          task={cur}
          index={phase.index}
          total={phase.tasks.length}
          chapterName={chapter?.name}
          themeName={theme?.name}
          showInstantFeedback={false}
          onAnswer={onAnswer}
        />
      </div>
    </div>
  )
}
