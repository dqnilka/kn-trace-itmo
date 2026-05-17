import { useState } from 'react'
import { invalidateBank } from '../state/bank'

/**
 * Узел n7 диаграммы: выбор серии экзамена ФСФР.
 *
 * MVP: на бэке пока только fsfr-basic. Здесь — мок-картинка для пользователя,
 * который видит линейку всех серий и выбирает свою. Внутри localStorage
 * сохраняем slug. Все остальные экраны пока продолжат работать с базовой
 * серией (см. ACTIVE_EXAM_SLUG в state/bank.ts), но визуально пользователь
 * прошёл «селектор».
 */

export type ExamSeries = {
  slug: string
  title: string
  short: string
  status: 'available' | 'coming_soon'
  description: string
}

export const SERIES: ExamSeries[] = [
  {
    slug: 'fsfr-basic',
    title: 'Базовый экзамен',
    short: 'Базовый',
    status: 'available',
    description:
      'Базовая программа специалиста финансового рынка. Допуск ко всем сериям 1.0–7.0.',
  },
  {
    slug: 'fsfr-1.0',
    title: 'Серия 1.0',
    short: '1.0',
    status: 'coming_soon',
    description: 'Брокерская деятельность и работа с клиентами.',
  },
  {
    slug: 'fsfr-2.0',
    title: 'Серия 2.0',
    short: '2.0',
    status: 'coming_soon',
    description: 'Дилерская и доверительное управление.',
  },
  {
    slug: 'fsfr-3.0',
    title: 'Серия 3.0',
    short: '3.0',
    status: 'coming_soon',
    description: 'Управление инвестиционными фондами.',
  },
  {
    slug: 'fsfr-4.0',
    title: 'Серия 4.0',
    short: '4.0',
    status: 'coming_soon',
    description: 'Депозитарная деятельность.',
  },
  {
    slug: 'fsfr-5.0',
    title: 'Серия 5.0',
    short: '5.0',
    status: 'coming_soon',
    description: 'Ведение реестра владельцев ценных бумаг.',
  },
  {
    slug: 'fsfr-6.0',
    title: 'Серия 6.0',
    short: '6.0',
    status: 'coming_soon',
    description: 'Деятельность специалистов организаторов торговли.',
  },
  {
    slug: 'fsfr-7.0',
    title: 'Серия 7.0',
    short: '7.0',
    status: 'coming_soon',
    description: 'Деятельность специалистов клиринга.',
  },
]

const KEY = 'akt:series'

export function loadSeries(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function saveSeries(slug: string): void {
  try {
    localStorage.setItem(KEY, slug)
  } catch {
    // ignore
  }
}

export default function ExamSeriesScreen({
  onDone,
}: {
  onDone: () => void
}) {
  const [picked, setPicked] = useState<string | null>(
    () => loadSeries() ?? 'fsfr-basic',
  )

  const confirm = () => {
    if (!picked) return
    // Если поменяли серию — сбрасываем закэшированный банк, чтобы
    // следующий loadBank() ушёл за новыми данными.
    const prev = loadSeries()
    if (prev && prev !== picked) {
      invalidateBank()
    }
    saveSeries(picked)
    onDone()
  }

  return (
    <div className="screen">
      <div className="screen-body narrow">
        <div className="screen-eyebrow">Шаг 1 из 2 · выбор серии</div>
        <h1 className="screen-title">Какую серию ФСФР готовим?</h1>
        <p className="screen-subtitle" style={{ maxWidth: 560 }}>
          У нас есть базовая программа специалиста и 7 специальных серий. Сейчас
          доступна только базовая — остальные подключим позже. Базовая обязательна
          как допуск к остальным.
        </p>

        <div className="series-grid">
          {SERIES.map((s) => {
            const available = s.status === 'available'
            const selected = picked === s.slug
            return (
              <button
                key={s.slug}
                type="button"
                disabled={!available}
                onClick={() => available && setPicked(s.slug)}
                className={`series-card ${selected ? 'selected' : ''} ${
                  available ? '' : 'disabled'
                }`}
              >
                <div className="series-card-head">
                  <div className="series-short">{s.short}</div>
                  {!available && (
                    <span className="chip chip-muted">скоро</span>
                  )}
                  {selected && available && (
                    <span className="chip chip-ok">выбрано</span>
                  )}
                </div>
                <div className="series-title">{s.title}</div>
                <div className="series-desc">{s.description}</div>
              </button>
            )
          })}
        </div>

        <div className="actions-row" style={{ marginTop: 22 }}>
          <button className="pill pill-primary big" onClick={confirm} disabled={!picked}>
            Продолжить → входной тест
          </button>
        </div>
      </div>
    </div>
  )
}
