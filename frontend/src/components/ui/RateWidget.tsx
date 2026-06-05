import { useState } from 'react'
import Icon from './Icon'
import Button from './Button'
import { api, isAbortError } from '../../api'

/**
 * Оценка контента (теория / занятие): лайк или дизлайк. При дизлайке —
 * необязательный комментарий «почему». Пишется в БД через /me/feedback.
 * Компонент дизайн-системы.
 */
export default function RateWidget({
  kind,
  refId = '',
  label = 'Насколько это было полезно?',
}: {
  kind: 'theory' | 'lesson'
  refId?: string
  label?: string
}) {
  const [picked, setPicked] = useState<null | 'like' | 'dislike'>(null)
  const [comment, setComment] = useState('')
  const [done, setDone] = useState(false)

  const send = async (rating: 'like' | 'dislike', withComment = false) => {
    try {
      await api.feedback({
        kind,
        ref: refId,
        rating,
        comment: withComment ? comment.trim() || undefined : undefined,
      })
    } catch (e) {
      if (!isAbortError(e)) {
        // best-effort: всё равно благодарим, не мешаем UX
      }
    }
    setDone(true)
  }

  if (done) {
    return <div className="rate-widget rate-done">Спасибо за оценку!</div>
  }

  return (
    <div className="rate-widget">
      <span className="rate-label">{label}</span>
      {picked !== 'dislike' ? (
        <div className="rate-btns">
          <button
            className="rate-btn"
            onClick={() => send('like')}
            aria-label="Полезно"
            title="Полезно"
          >
            <Icon name="like" size={18} /> Полезно
          </button>
          <button
            className="rate-btn"
            onClick={() => setPicked('dislike')}
            aria-label="Не помогло"
            title="Не помогло"
          >
            <Icon name="dislike" size={18} /> Не помогло
          </button>
        </div>
      ) : (
        <div className="rate-comment">
          <textarea
            className="field-input rate-textarea"
            placeholder="Что не так? (необязательно)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
          />
          <div className="rate-comment-actions">
            <Button variant="secondary" onClick={() => setPicked(null)}>
              Отмена
            </Button>
            <Button onClick={() => send('dislike', true)}>Отправить</Button>
          </div>
        </div>
      )}
    </div>
  )
}
