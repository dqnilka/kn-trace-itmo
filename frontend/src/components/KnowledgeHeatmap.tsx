import type { BankEntranceResult } from '../types'

/**
 * Heatmap карты знаний по главам (узел n15 диаграммы).
 *
 * Считаем по входному тесту: для каждой главы — accuracy = correct/asked.
 * Главы без ответов — серые («?»).
 */
function colorFor(pct: number | null): string {
  if (pct == null) return 'var(--bg-3)'
  if (pct >= 0.8) return '#16a34a'
  if (pct >= 0.6) return '#84cc16'
  if (pct >= 0.4) return '#f59e0b'
  if (pct >= 0.2) return '#fb923c'
  return '#ef4444'
}

export default function KnowledgeHeatmap({
  result,
  totalChapters,
}: {
  result: BankEntranceResult
  totalChapters?: number
}) {
  const chapters = Object.values(result.per_chapter).sort(
    (a, b) => a.chapter_id - b.chapter_id,
  )
  // Если знаем общее число глав банка, добавляем «непокрытые» как «?»
  const ghosts =
    totalChapters && totalChapters > chapters.length
      ? Array.from({ length: totalChapters - chapters.length }, (_, i) => ({
          chapter_id: -1 - i,
          chapter_name: '—',
          asked: 0,
          wrong: 0,
        }))
      : []

  const cells = [
    ...chapters.map((c) => {
      const pct = c.asked > 0 ? (c.asked - c.wrong) / c.asked : null
      return {
        id: c.chapter_id,
        label: c.chapter_name,
        pct,
        asked: c.asked,
        correct: c.asked - c.wrong,
      }
    }),
    ...ghosts.map((g) => ({
      id: g.chapter_id,
      label: 'не проверено',
      pct: null as number | null,
      asked: 0,
      correct: 0,
    })),
  ]

  return (
    <div className="heatmap">
      <div className="heatmap-title">Карта знаний по {cells.length} главам</div>
      <div className="heatmap-grid">
        {cells.map((c, i) => {
          const pct = c.pct
          const pctTxt = pct == null ? '?' : `${Math.round(pct * 100)}%`
          return (
            <div
              key={c.id}
              className="heatmap-cell"
              style={{ background: colorFor(pct) }}
              title={
                c.asked > 0
                  ? `${c.label}: ${c.correct} из ${c.asked} верно`
                  : `${c.label}: не проверено`
              }
            >
              <div className="heatmap-cell-id">{i + 1}</div>
              <div className="heatmap-cell-pct">{pctTxt}</div>
            </div>
          )
        })}
      </div>
      <div className="heatmap-legend">
        <span><i style={{ background: '#ef4444' }} /> 0-20%</span>
        <span><i style={{ background: '#fb923c' }} /> 20-40%</span>
        <span><i style={{ background: '#f59e0b' }} /> 40-60%</span>
        <span><i style={{ background: '#84cc16' }} /> 60-80%</span>
        <span><i style={{ background: '#16a34a' }} /> 80-100%</span>
        <span><i style={{ background: 'var(--bg-3)' }} /> не проверено</span>
      </div>
    </div>
  )
}
