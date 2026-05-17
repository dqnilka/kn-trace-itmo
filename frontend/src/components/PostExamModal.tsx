import { useEffect, useState } from 'react'

/**
 * Узлы pe1-pe6 диаграммы fsfr-user-flow v2.
 *
 * Модалка «Как прошёл экзамен?» — открывается через 24 часа после того, как
 * пользователь нажал «Я сдал(а) экзамен» в RealExamPrepScreen. Для демо у нас
 * есть «принудительный» режим (force=true), чтобы можно было увидеть модалку
 * сразу без ожидания.
 */

const TAKEN_KEY = 'akt:exam_taken_at'
const ANSWERED_KEY = 'akt:exam_postsurvey_answered'

export function markExamTaken(): void {
  try {
    localStorage.setItem(TAKEN_KEY, new Date().toISOString())
    localStorage.removeItem(ANSWERED_KEY)
  } catch {
    // ignore
  }
}

export function shouldShowPostExam(): boolean {
  try {
    const taken = localStorage.getItem(TAKEN_KEY)
    const answered = localStorage.getItem(ANSWERED_KEY)
    if (!taken || answered) return false
    const dt = new Date(taken)
    if (Number.isNaN(dt.getTime())) return false
    return Date.now() - dt.getTime() >= 24 * 3600 * 1000
  } catch {
    return false
  }
}

export function markPostExamAnswered(): void {
  try {
    localStorage.setItem(ANSWERED_KEY, new Date().toISOString())
  } catch {
    // ignore
  }
}

type Step = 'ask' | 'congrats' | 'support'

export default function PostExamModal({
  force,
  onClose,
  onRetry,
}: {
  force?: boolean
  onClose: () => void
  onRetry: () => void
}) {
  const [open, setOpen] = useState<boolean>(false)
  const [step, setStep] = useState<Step>('ask')

  useEffect(() => {
    setOpen(!!force || shouldShowPostExam())
  }, [force])

  if (!open) return null

  const close = () => {
    markPostExamAnswered()
    setOpen(false)
    onClose()
  }

  return (
    <div className="modal-overlay" onClick={close}>
      <div
        className="modal post-exam-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {step === 'ask' && (
          <>
            <div style={{ fontSize: 40 }}>🎓</div>
            <h2>Как прошёл экзамен?</h2>
            <p className="muted">
              Прошло 24 часа с твоего экзамена. Очень важно зафиксировать
              результат — независимо от исхода. Если получилось — обсудим, что
              сработало; если нет — спокойно разберём и подготовимся к пересдаче.
            </p>
            <div className="actions-row" style={{ marginTop: 18 }}>
              <button
                className="pill pill-primary big"
                onClick={() => setStep('congrats')}
              >
                Сдал(а) ✅
              </button>
              <button className="pill" onClick={() => setStep('support')}>
                Не сдал(а)
              </button>
            </div>
          </>
        )}

        {step === 'congrats' && (
          <>
            <div style={{ fontSize: 56 }}>🎉</div>
            <h2>Поздравляем!</h2>
            <p style={{ lineHeight: 1.6 }}>
              Ты сдал(а) экзамен. Это твой результат — модель только подсветила,
              где работать. На радостях можно отдохнуть сутки, потом — выбрать
              следующую серию (1.0–7.0) и начать ту же траекторию заново.
            </p>
            <div className="actions-row" style={{ marginTop: 18, justifyContent: 'center' }}>
              <button className="pill pill-primary big" onClick={close}>
                Спасибо, закрыть
              </button>
            </div>
          </>
        )}

        {step === 'support' && (
          <>
            <div style={{ fontSize: 48 }}>🤝</div>
            <h2>Это не финал</h2>
            <p style={{ lineHeight: 1.6 }}>
              Не сдалось — бывает, и это не отменяет всю проделанную работу.
              Большинство сдают со второй попытки за 2-3 недели спокойной
              доработки. Давай разберём, что именно подвело, и составим
              мини-план на пересдачу.
            </p>
            <ul className="muted" style={{ lineHeight: 1.7, fontSize: 13 }}>
              <li>Пересдача обычно открывается через 14 дней.</li>
              <li>Авто-план будет короче — только провальные главы.</li>
              <li>Mock и финишную прямую запустим за неделю до даты.</li>
            </ul>
            <div className="actions-row" style={{ marginTop: 18 }}>
              <button
                className="pill pill-primary"
                onClick={() => {
                  markPostExamAnswered()
                  setOpen(false)
                  onRetry()
                }}
              >
                Запустить план пересдачи →
              </button>
              <button className="pill" onClick={close}>
                Позже
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
