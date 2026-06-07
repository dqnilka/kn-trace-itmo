import type {
  BankEntranceResult,
  BankTheme,
  ExamBank,
  ExamVariantSummary,
  MasteryStore,
} from '../types'

const KEY = 'akt:mastery'
const VARIANTS_KEY = 'akt:variants'

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, v: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(v))
  } catch {
    // ignore
  }
}

export function loadMastery(): MasteryStore {
  return read<MasteryStore>(KEY, {})
}

export function saveMastery(m: MasteryStore): void {
  write(KEY, m)
}

export function clearMastery(): void {
  try {
    localStorage.removeItem(KEY)
    localStorage.removeItem(VARIANTS_KEY)
  } catch {
    // ignore
  }
}

export function bumpMastery(
  store: MasteryStore,
  theme_code: string,
  is_correct: boolean,
): MasteryStore {
  const prev = store[theme_code] ?? {
    asked: 0,
    correct: 0,
    last_practiced: new Date(0).toISOString(),
  }
  return {
    ...store,
    [theme_code]: {
      asked: prev.asked + 1,
      correct: prev.correct + (is_correct ? 1 : 0),
      last_practiced: new Date().toISOString(),
    },
  }
}

export function applyEntrance(
  store: MasteryStore,
  result: BankEntranceResult,
): MasteryStore {
  let out = { ...store }
  const now = new Date().toISOString()
  for (const a of result.answers) {
    const prev = out[a.theme_code] ?? {
      asked: 0,
      correct: 0,
      last_practiced: now,
    }
    out[a.theme_code] = {
      asked: prev.asked + 1,
      correct: prev.correct + (a.is_correct ? 1 : 0),
      last_practiced: now,
    }
  }
  return out
}

/** Theme accuracy as a 0..1 number, or null if no data. */
export function themePct(store: MasteryStore, theme_code: string): number | null {
  const m = store[theme_code]
  if (!m || m.asked === 0) return null
  return m.correct / m.asked
}

// Confidence thresholds: how many answers we need before the mastery number is
// trustworthy enough to display as a colored level rather than a "?".
export const THEME_MIN_CONFIDENT = 3
export const CHAPTER_MIN_CONFIDENT = 6
export const OVERALL_MIN_CONFIDENT = 20

export type Confidence = 'empty' | 'low' | 'ok'

export type ScoreInfo = {
  asked: number
  correct: number
  pct: number | null
  confidence: Confidence
}

function scoreInfo(asked: number, correct: number, min_confident: number): ScoreInfo {
  if (asked === 0) {
    return { asked: 0, correct: 0, pct: null, confidence: 'empty' }
  }
  const pct = correct / asked
  return {
    asked,
    correct,
    pct,
    confidence: asked < min_confident ? 'low' : 'ok',
  }
}

export function themeScore(store: MasteryStore, theme_code: string): ScoreInfo {
  const m = store[theme_code]
  if (!m) return scoreInfo(0, 0, THEME_MIN_CONFIDENT)
  return scoreInfo(m.asked, m.correct, THEME_MIN_CONFIDENT)
}

export function chapterScore(store: MasteryStore, themes: BankTheme[]): ScoreInfo {
  let asked = 0
  let correct = 0
  for (const t of themes) {
    const m = store[t.code]
    if (!m) continue
    asked += m.asked
    correct += m.correct
  }
  return scoreInfo(asked, correct, CHAPTER_MIN_CONFIDENT)
}

export function overallScore(store: MasteryStore): ScoreInfo {
  let asked = 0
  let correct = 0
  for (const k of Object.keys(store)) {
    asked += store[k].asked
    correct += store[k].correct
  }
  return scoreInfo(asked, correct, OVERALL_MIN_CONFIDENT)
}

/** Chapter accuracy = weighted by themes that have data; null if nothing asked. */
export function chapterPct(
  store: MasteryStore,
  themes: BankTheme[],
): { pct: number | null; asked: number; correct: number } {
  let asked = 0
  let correct = 0
  for (const t of themes) {
    const m = store[t.code]
    if (!m) continue
    asked += m.asked
    correct += m.correct
  }
  if (asked === 0) return { pct: null, asked: 0, correct: 0 }
  return { pct: correct / asked, asked, correct }
}

export function overallStats(store: MasteryStore): {
  asked: number
  correct: number
  pct: number | null
} {
  let asked = 0
  let correct = 0
  for (const k of Object.keys(store)) {
    asked += store[k].asked
    correct += store[k].correct
  }
  if (asked === 0) return { asked: 0, correct: 0, pct: null }
  return { asked, correct, pct: correct / asked }
}

/**
 * Pick weakest themes for the adaptive session.
 * Priority: untouched themes first (they're unknown), then lowest accuracy,
 * tie-break by chapter size (larger first — bigger impact on exam).
 */
export function pickWeakThemes(
  store: MasteryStore,
  bank: ExamBank,
  count: number,
  tasksByTheme: Map<string, number>,
): BankTheme[] {
  const scored = bank.themes
    .filter((t) => (tasksByTheme.get(t.code) ?? 0) > 0)
    .map((t) => {
      const m = store[t.code]
      const pct = !m || m.asked === 0 ? null : m.correct / m.asked
      // untouched themes are highest priority
      const priority = pct == null ? -1 : pct
      const size = tasksByTheme.get(t.code) ?? 0
      return { t, priority, size }
    })
  scored.sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority
    return b.size - a.size
  })
  return scored.slice(0, count).map((x) => x.t)
}

// === Exam variants history ===

export function loadVariants(): ExamVariantSummary[] {
  return read<ExamVariantSummary[]>(VARIANTS_KEY, [])
}

export function saveVariants(list: ExamVariantSummary[]): void {
  write(VARIANTS_KEY, list)
}

export function pushVariant(s: ExamVariantSummary): void {
  const list = loadVariants()
  list.push(s)
  saveVariants(list)
}

// === Seeded sample (deterministic per variant_id) ===

function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function seededSample<T>(items: T[], n: number, seed: number): T[] {
  if (n >= items.length) return items.slice()
  const rng = mulberry32(seed)
  const idxs: number[] = []
  const taken = new Set<number>()
  while (idxs.length < n) {
    const i = Math.floor(rng() * items.length)
    if (!taken.has(i)) {
      taken.add(i)
      idxs.push(i)
    }
  }
  return idxs.map((i) => items[i])
}
