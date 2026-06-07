import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import InfoTip from '../components/InfoTip'
import Icon from '../components/ui/Icon'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import ProgressRing from '../components/ui/ProgressRing'
import { ACTIVE_EXAM_SLUG, buildIndex, loadBank } from '../state/bank'
import {
  CHAPTER_MIN_CONFIDENT,
  OVERALL_MIN_CONFIDENT,
  THEME_MIN_CONFIDENT,
  chapterScore,
  loadMastery,
  loadVariants,
  overallScore,
  themeScore,
  type ScoreInfo,
} from '../state/mastery'
import type {
  BankChapter,
  BankTheme,
  ExamBank,
  ExamVariantSummary,
  MasteryResponse,
  MasteryStore,
  UserState,
} from '../types'

type Tab = 'topics' | 'variants'

const VARIANTS = [
  { id: 1, title: 'Пробный вариант №1', difficulty: 'Стандарт' },
  { id: 2, title: 'Пробный вариант №2', difficulty: 'Стандарт' },
  { id: 3, title: 'Пробный вариант №3', difficulty: 'Усложнённый' },
  { id: 4, title: 'Пробный вариант №4', difficulty: 'Финальный' },
]

const PASS_THRESHOLD = 80

// Knowledge level on a 0-100 "will-I-pass" scale.
function knowledgeLevel(pct: number): number {
  return Math.max(0, Math.min(100, Math.round(pct * 100)))
}

export default function DashboardScreen({
  user,
  onAdaptive,
  onPractice,
  onTheory,
  onExamVariant,
  onLogout,
  onRetakeEntrance,
  hasEntranceResults,
}: {
  user: UserState
  onAdaptive: () => void
  onPractice: (themeCode: string) => void
  onTheory: (themeCode: string) => void
  onExamVariant: (variantId: number) => void
  onLogout: () => void
  onRetakeEntrance: () => void
  hasEntranceResults: boolean
}) {
  const [tab, setTab] = useState<Tab>('topics')
  const [confirmRetake, setConfirmRetake] = useState(false)
  const [bank, setBank] = useState<ExamBank | null>(null)
  const [mastery, setMastery] = useState<MasteryStore>(() => loadMastery())
  const [bktMastery, setBktMastery] = useState<MasteryResponse | null>(null)
  const [variants, setVariants] = useState<ExamVariantSummary[]>(() =>
    loadVariants(),
  )
  const [search, setSearch] = useState('')
  const [openChapters, setOpenChapters] = useState<Record<number, boolean>>({})

  useEffect(() => {
    loadBank()
      .then(setBank)
      .catch(() => setBank(null))
  }, [])

  // Fetch BKT-driven mastery from the backend (calibrated ML model, not the
  // raw correct/asked counters in localStorage). Re-fetched on window focus
  // so the dashboard reflects answers given in another tab / practice.
  useEffect(() => {
    let cancelled = false
    const fetchBkt = () => {
      api
        .mastery(ACTIVE_EXAM_SLUG, user.id)
        .then((r) => {
          if (!cancelled) setBktMastery(r)
        })
        .catch(() => {
          /* server mastery is best-effort */
        })
    }
    fetchBkt()
    window.addEventListener('focus', fetchBkt)
    return () => {
      cancelled = true
      window.removeEventListener('focus', fetchBkt)
    }
  }, [user.id])

  // Refresh from localStorage on visibility — helps when returning from practice.
  useEffect(() => {
    const onFocus = () => {
      setMastery(loadMastery())
      setVariants(loadVariants())
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  const index = useMemo(() => (bank ? buildIndex(bank) : null), [bank])
  const overall = useMemo(() => overallScore(mastery), [mastery])

  const themesByChapter = useMemo(() => {
    const m = new Map<number, BankTheme[]>()
    bank?.themes.forEach((t) => {
      if (!m.has(t.chapter_id)) m.set(t.chapter_id, [])
      m.get(t.chapter_id)!.push(t)
    })
    return m
  }, [bank])

  const filteredChapters = useMemo(() => {
    if (!bank) return []
    if (!search.trim()) return bank.chapters
    const q = search.toLowerCase()
    const chaptersWithHit = new Set<number>()
    for (const t of bank.themes) {
      if (t.name.toLowerCase().includes(q)) chaptersWithHit.add(t.chapter_id)
    }
    for (const c of bank.chapters) {
      if (c.name.toLowerCase().includes(q)) chaptersWithHit.add(c.id)
    }
    return bank.chapters.filter((c) => chaptersWithHit.has(c.id))
  }, [bank, search])

  const themesOfChapter = (chapterId: number): BankTheme[] => {
    const list = themesByChapter.get(chapterId) ?? []
    const q = search.trim().toLowerCase()
    if (!q) return list
    return list.filter((t) => t.name.toLowerCase().includes(q))
  }

  // Recommended weakest theme — used for hero subtitle
  const recommendedTheme = useMemo(() => {
    if (!index) return null
    const scored = (bank?.themes ?? [])
      .map((t) => {
        const tasks = index.tasksByTheme.get(t.code)?.length ?? 0
        if (tasks === 0) return null
        const s = themeScore(mastery, t.code)
        // untouched themes are highest priority
        const priority = s.pct == null ? -1 : s.pct
        return { t, priority, tasks }
      })
      .filter((x): x is { t: BankTheme; priority: number; tasks: number } => !!x)
    scored.sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority
      return b.tasks - a.tasks
    })
    return scored[0]?.t ?? null
  }, [index, bank, mastery])

  const totalThemes = bank?.themes.length ?? 0
  const touchedThemes = Object.keys(mastery).length

  return (
    <div className="screen dashboard-screen">
      <ConfirmDialog
        open={confirmRetake}
        title="Пройти входной тест заново?"
        text="Текущая карта знаний пересчитается по новым ответам."
        confirmLabel="Пройти заново"
        cancelLabel="Отмена"
        onConfirm={onRetakeEntrance}
        onCancel={() => setConfirmRetake(false)}
      />
      <div className="page-head">
        <div>
          <div className="page-eyebrow">Привет, {user.name}</div>
          <h1 className="page-title">Тренажёр</h1>
        </div>
        <div className="page-actions">
          <button
            className="link-button"
            onClick={() =>
              hasEntranceResults ? setConfirmRetake(true) : onRetakeEntrance()
            }
          >
            {hasEntranceResults ? 'пройти входной заново' : 'пройти входной'}
          </button>
          <button className="link-button" onClick={onLogout}>
            выход
          </button>
        </div>
      </div>

      <div className="subject-row">
        <span className="subject-pill active">Базовый ФСФР</span>
        <button className="subject-pill disabled" disabled>
          Серия 1.0
        </button>
        <button className="subject-pill disabled" disabled>
          Серия 2.0
        </button>
      </div>

      {/* Hero CTA — главный путь обучения */}
      <div className="hero-card">
        <div className="hero-body">
          <div className="hero-eyebrow">Сегодняшнее занятие</div>
          <h2 className="hero-title">
            {recommendedTheme
              ? `Старт с темы «${recommendedTheme.name}»`
              : 'Адаптивный курс'}
          </h2>
          <p className="hero-sub">
            Сначала короткая теория, затем 2–3 практики. Идём по темам, где у
            тебя самые большие пробелы.
          </p>
          {!hasEntranceResults && (
            <button className="hero-hint" onClick={onRetakeEntrance}>
              Пройти входной тест — чтобы точнее найти слабые темы
            </button>
          )}
        </div>
        <button className="pill pill-primary big" onClick={onAdaptive}>
          Начать занятие →
        </button>
      </div>

      <div className="stat-row">
        <StatCard
          label="Уровень знаний"
          tooltip={
            'BKT-оценка (Bayesian Knowledge Tracing): не просто «верных/всего», ' +
            'а вероятностная модель освоения по всем 550+ концептам графа. ' +
            'Шкала 0-100, где ≥80 — условно сдашь экзамен. Точность растёт с числом ответов.'
          }
          value={
            overall.confidence === 'ok'
              ? knowledgeLevel(bktMastery?.overall ?? overall.pct ?? 0)
              : null
          }
          confidence={overall.confidence}
          sub={
            overall.asked === 0
              ? 'нет данных — начни занятие'
              : overall.confidence === 'low'
                ? `мало данных (${overall.asked} из ${OVERALL_MIN_CONFIDENT})`
                : `на основе ${overall.asked} ${plural(overall.asked, 'ответа', 'ответов', 'ответов')}`
          }
          targetMark={PASS_THRESHOLD}
        />
        <StatCard
          label="Изучено тем"
          tooltip={
            'Сколько тем уже было задействовано — хотя бы один ответ. ' +
            'Хорошее покрытие важно для финального уровня знаний.'
          }
          value={touchedThemes}
          confidence={totalThemes > 0 ? 'ok' : 'empty'}
          maxValue={totalThemes}
          sub={`${touchedThemes} из ${totalThemes}`}
        />
        <StatCard
          label="Пробные варианты"
          tooltip={
            'История пробных экзаменов: 50 вопросов, без подсказок. Проходной уровень — 80. ' +
            'Помогает понять реальную готовность.'
          }
          value={
            variants.length > 0
              ? Math.round(
                  (variants[variants.length - 1].correct /
                    variants[variants.length - 1].total) *
                    100,
                )
              : null
          }
          confidence={variants.length > 0 ? 'ok' : 'empty'}
          sub={
            variants.length === 0
              ? 'ещё не проходил'
              : `${variants.length} ${variants.length === 1 ? 'попытка' : 'попыток'} · последний`
          }
          link={
            <button
              className="link-button stat-link"
              onClick={() => setTab('variants')}
            >
              к вариантам →
            </button>
          }
        />
      </div>

      <nav className="trainer-tabs">
        <button
          className={tab === 'topics' ? 'active' : ''}
          onClick={() => setTab('topics')}
        >
          Темы
        </button>
        <button
          className={tab === 'variants' ? 'active' : ''}
          onClick={() => setTab('variants')}
        >
          Пробные варианты
        </button>
      </nav>

      {tab === 'topics' && (
        <div className="topics-tab">
          <div className="search-box">
            <span className="search-icon"><Icon name="search" size={17} /></span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по разделам и темам..."
            />
          </div>
          {!bank && <p className="meta">Загружаем структуру курса…</p>}
          {bank && index && (
            <div className="chapter-grid">
              {filteredChapters.map((c) => (
                <ChapterCard
                  key={c.id}
                  chapter={c}
                  themes={themesOfChapter(c.id)}
                  mastery={mastery}
                  bkt={bktMastery}
                  open={openChapters[c.id] ?? !!search}
                  onToggle={() =>
                    setOpenChapters((p) => ({
                      ...p,
                      [c.id]: !(p[c.id] ?? !!search),
                    }))
                  }
                  tasksByTheme={index.tasksByTheme}
                  onPractice={onPractice}
                  onTheory={onTheory}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'variants' && bank && index && (
        <VariantsTab variants={variants} onPick={onExamVariant} />
      )}
    </div>
  )
}

function ChapterCard({
  chapter,
  themes,
  mastery,
  bkt,
  open,
  onToggle,
  tasksByTheme,
  onPractice,
  onTheory,
}: {
  chapter: BankChapter
  themes: BankTheme[]
  mastery: MasteryStore
  bkt: MasteryResponse | null
  open: boolean
  onToggle: () => void
  tasksByTheme: Map<string, { id: number }[]> | Map<string, unknown[]>
  onPractice: (code: string) => void
  onTheory: (code: string) => void
}) {
  // Touch count comes from local answers; the displayed level uses server BKT.
  const ch = chapterScore(mastery, themes)
  const bktPct = bkt?.by_chapter?.[String(chapter.id)] ?? null
  const levelPct = ch.confidence === 'ok' ? (bktPct ?? ch.pct ?? null) : null
  const headStateClass =
    ch.confidence === 'empty' || ch.confidence === 'low'
      ? 'untouched'
      : levelPct != null && levelPct >= 0.75
        ? 'strong'
        : levelPct != null && levelPct >= 0.5
          ? 'medium'
          : 'weak'

  const subtitle =
    ch.confidence === 'empty'
      ? `${themes.length} ${plural(themes.length, 'тема', 'темы', 'тем')} · не начат`
      : ch.confidence === 'low'
        ? `${themes.length} ${plural(themes.length, 'тема', 'темы', 'тем')} · ${ch.asked} ${plural(ch.asked, 'ответ', 'ответа', 'ответов')} — нужно ${CHAPTER_MIN_CONFIDENT}+ для оценки`
        : `${themes.length} ${plural(themes.length, 'тема', 'темы', 'тем')} · ${ch.asked} ${plural(ch.asked, 'ответ', 'ответа', 'ответов')}`

  return (
    <div className={`chapter-card ${open ? 'open' : ''} ${headStateClass}`}>
      <button className="chapter-head" onClick={onToggle}>
        <div className="chapter-left">
          <DashboardProgressRing value={levelPct != null ? Math.round(levelPct * 100) : null} size={44} />
          <div>
            <div className="chapter-title">
              {chapter.num}. {chapter.name}
            </div>
            <div className="chapter-sub">{subtitle}</div>
          </div>
        </div>
        <span className="chev">{open ? '⌃' : '⌄'}</span>
      </button>
      {open && (
        <div className="theme-list">
          {themes.map((t) => {
            const taskCount = (tasksByTheme.get(t.code) as unknown[] | undefined)?.length ?? 0
            const s = themeScore(mastery, t.code)
            const bktThemePct = bkt?.by_theme?.[t.code] ?? null
            const themePctVal =
              s.confidence === 'ok' ? (bktThemePct ?? s.pct ?? null) : null
            const stateClass =
              s.confidence === 'empty' || s.confidence === 'low'
                ? 'untouched'
                : themePctVal != null && themePctVal >= 0.75
                  ? 'strong'
                  : themePctVal != null && themePctVal >= 0.5
                    ? 'medium'
                    : 'weak'
            return (
              <div key={t.id} className={`theme-card ${stateClass}`}>
                <div className="theme-left">
                  <MasteryBadge score={s} bktPct={bktThemePct} />
                  <div>
                    <div className="theme-name">{t.name}</div>
                    <div className="theme-meta">
                      {t.code} · {taskCount} {plural(taskCount, 'вопрос', 'вопроса', 'вопросов')}
                    </div>
                  </div>
                </div>
                <div className="theme-actions">
                  <button
                    className="pill pill-cta"
                    onClick={() => onPractice(t.code)}
                    disabled={taskCount === 0}
                  >
                    Решать
                  </button>
                  <button className="pill pill-ghost" onClick={() => onTheory(t.code)}>
                    Изучать
                  </button>
                </div>
              </div>
            )
          })}
          {themes.length === 0 && (
            <div className="meta padded">В этом разделе нет тем под запрос.</div>
          )}
        </div>
      )}
    </div>
  )
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

function VariantsTab({
  variants,
  onPick,
}: {
  variants: ExamVariantSummary[]
  onPick: (id: number) => void
}) {
  const byId = new Map<number, ExamVariantSummary>()
  for (const v of variants) byId.set(v.variant_id, v)

  return (
    <div className="variants-grid">
      {VARIANTS.map((v) => {
        const past = byId.get(v.id)
        return (
          <div key={v.id} className="variant-card">
            <div className="variant-title">{v.title}</div>
            <div className="variant-meta">
              <span className="chip chip-soft">{v.difficulty}</span>
              {past && <VariantResultChip summary={past} />}
            </div>
            <p className="variant-desc">
              50 вопросов, без подсказок. После завершения — разбор ошибок по
              разделам.
            </p>
            <button className="pill pill-cta" onClick={() => onPick(v.id)}>
              {past ? 'Пересдать' : 'Выполнить'}
            </button>
          </div>
        )
      })}
    </div>
  )
}

function VariantResultChip({ summary }: { summary: ExamVariantSummary }) {
  const plannedTotal = summary.planned_total ?? summary.total
  const pct = summary.total > 0 ? Math.round((summary.correct / summary.total) * 100) : 0
  if (summary.status === 'early') {
    return (
      <span className="chip chip-muted">
        досрочно · {summary.total}/{plannedTotal}
      </span>
    )
  }
  if (summary.status === 'timeout') {
    return (
      <span className="chip chip-muted">
        время вышло · {summary.total}/{plannedTotal}
      </span>
    )
  }
  return (
    <span className={`chip ${pct >= 80 ? 'chip-ok' : 'chip-muted'}`}>
      уровень {pct}
    </span>
  )
}

function MasteryBadge({
  score,
  bktPct,
}: {
  score: ScoreInfo
  bktPct: number | null
}) {
  // Unified "?" for both empty and low-confidence — user can't intuitively tell
  // the difference between "не пробовал" and "пробовал, но мало". Tooltip
  // explains either case.
  if (score.confidence !== 'ok') {
    const help =
      score.asked === 0
        ? 'Решений в этой теме нет. Нажми «Решать», чтобы начать.'
        : `Решено ${score.asked} ${plural(score.asked, 'задача', 'задачи', 'задач')} из ${THEME_MIN_CONFIDENT}+, нужных для оценки.`
    return (
      <InfoTip
        text={help}
        label="?"
        size="md"
        className="progress-ring-tip progress-ring-tip-sm"
      />
    )
  }
  // Confident mastery: prefer server BKT posterior, fall back to count-based pct.
  const pct = (bktPct != null ? bktPct : (score.pct ?? 0)) * 100
  const rounded = Math.round(pct)
  return (
    <DashboardProgressRing
      value={rounded}
      size={44}
      label={`${rounded}`}
      title={`Уровень знаний ${Math.round(pct)} по BKT-модели (${score.asked} ${plural(score.asked, 'ответ', 'ответа', 'ответов')})`}
    />
  )
}

function progressTone(value: number | null): 'accent' | 'ok' | 'warn' | 'neutral' {
  if (value == null) return 'neutral'
  if (value >= 75) return 'ok'
  if (value >= 50) return 'warn'
  return 'accent'
}

function DashboardProgressRing({
  value,
  size = 56,
  label,
  title,
}: {
  value: number | null
  size?: number
  label?: string
  title?: string
}) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <ProgressRing
      value={value == null ? null : v / 100}
      tone={progressTone(value)}
      size={size}
      stroke={size <= 44 ? 5 : 7}
      label={label ?? (value == null ? '?' : String(v))}
      title={title}
      className={size <= 44 ? 'dashboard-ring dashboard-ring-sm' : 'dashboard-ring'}
    />
  )
}

function StatCard({
  label,
  tooltip,
  value,
  confidence,
  sub,
  link,
  targetMark,
  maxValue,
}: {
  label: string
  tooltip: string
  value: number | null
  confidence: 'empty' | 'low' | 'ok'
  sub: string
  link?: React.ReactNode
  targetMark?: number
  maxValue?: number
}) {
  const showQuestion = confidence !== 'ok' || value == null
  const ringValue =
    showQuestion
      ? null
      : maxValue != null && maxValue > 0
        ? Math.round((value / maxValue) * 100)
        : value
  const ringLabel = showQuestion ? '?' : maxValue != null ? String(value) : String(value)
  return (
    <div className="stat-card">
      <div className="stat-body">
        <div className="stat-label-row">
          <div className="stat-label">{label}</div>
          <InfoTip text={tooltip} align="left" />
        </div>
        <div className="stat-sub">{sub}</div>
        {targetMark != null && (
          <div className="stat-target">проходной — {targetMark}</div>
        )}
        {link}
      </div>
      <div className="stat-ring">
        <DashboardProgressRing
          value={ringValue}
          size={64}
          label={ringLabel}
          title={maxValue != null && value != null ? `${value}/${maxValue}` : undefined}
        />
      </div>
    </div>
  )
}
