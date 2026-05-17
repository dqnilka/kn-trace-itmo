import { api, type FetchOpts } from '../api'
import type {
  BankChapter,
  BankTask,
  BankTheme,
  ExamBank,
} from '../types'

export const ACTIVE_EXAM_SLUG = 'fsfr-basic'

/**
 * Кэш банков по slug. Раньше был один глобальный `cache` — это блокировало
 * переключение серии на лету (вызов `loadBank('fsfr-1.0')` после загрузки
 * базовой получал бы базовый банк из кэша). Теперь — `Map<slug, ExamBank>`.
 */
const cache = new Map<string, ExamBank>()
const inflight = new Map<string, Promise<ExamBank>>()

export async function loadBank(
  slug: string = ACTIVE_EXAM_SLUG,
  opts?: FetchOpts,
): Promise<ExamBank> {
  const cached = cache.get(slug)
  if (cached) return cached
  const pending = inflight.get(slug)
  if (pending) return pending
  const p = api
    .examBank(slug, opts)
    .then((b) => {
      cache.set(slug, b)
      return b
    })
    .finally(() => {
      inflight.delete(slug)
    })
  inflight.set(slug, p)
  return p
}

/**
 * Сбросить кэш банка. Вызвать после смены серии экзамена.
 *
 * @param slug — какой именно сбросить; без аргумента — все.
 */
export function invalidateBank(slug?: string): void {
  if (slug) {
    cache.delete(slug)
    inflight.delete(slug)
  } else {
    cache.clear()
    inflight.clear()
  }
  indexCache = null
}

export type BankIndex = {
  bank: ExamBank
  chaptersById: Map<number, BankChapter>
  themesByCode: Map<string, BankTheme>
  tasksByTheme: Map<string, BankTask[]>
  tasksByChapter: Map<number, BankTask[]>
}

let indexCache: BankIndex | null = null

export function buildIndex(bank: ExamBank): BankIndex {
  if (indexCache && indexCache.bank === bank) return indexCache
  const chaptersById = new Map<number, BankChapter>(
    bank.chapters.map((c) => [c.id, c]),
  )
  const themesByCode = new Map<string, BankTheme>(
    bank.themes.map((t) => [t.code, t]),
  )
  const tasksByTheme = new Map<string, BankTask[]>()
  const tasksByChapter = new Map<number, BankTask[]>()
  for (const t of bank.tasks) {
    if (!tasksByTheme.has(t.theme_code)) tasksByTheme.set(t.theme_code, [])
    tasksByTheme.get(t.theme_code)!.push(t)
    const theme = themesByCode.get(t.theme_code)
    if (theme) {
      if (!tasksByChapter.has(theme.chapter_id))
        tasksByChapter.set(theme.chapter_id, [])
      tasksByChapter.get(theme.chapter_id)!.push(t)
    }
  }
  indexCache = { bank, chaptersById, themesByCode, tasksByTheme, tasksByChapter }
  return indexCache
}

function shuffle<T>(arr: T[]): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/**
 * Build a proportional sample across chapters.
 * Each chapter contributes at least 1 task; the rest are distributed proportionally.
 */
export function sampleEntrance(
  index: BankIndex,
  targetSize: number,
): BankTask[] {
  const totalTasks = index.bank.tasks.length
  if (totalTasks === 0) return []
  const picks: BankTask[] = []
  const chapters = index.bank.chapters
  // ideal quota per chapter
  const quotas = new Map<number, number>()
  let pickedSoFar = 0
  for (const c of chapters) {
    const tasksInCh = index.tasksByChapter.get(c.id)?.length ?? 0
    if (tasksInCh === 0) {
      quotas.set(c.id, 0)
      continue
    }
    const ideal = Math.max(1, Math.round((tasksInCh / totalTasks) * targetSize))
    quotas.set(c.id, ideal)
    pickedSoFar += ideal
  }
  // adjust: trim from largest if oversubscribed, top up smallest if undersubscribed
  let delta = pickedSoFar - targetSize
  while (delta !== 0) {
    const entries = Array.from(quotas.entries()).filter(([, q]) => q > 0)
    if (entries.length === 0) break
    if (delta > 0) {
      entries.sort((a, b) => b[1] - a[1])
      const [cid] = entries[0]
      quotas.set(cid, Math.max(1, quotas.get(cid)! - 1))
      delta -= 1
      if (quotas.get(cid)! <= 1) break
    } else {
      entries.sort((a, b) => a[1] - b[1])
      const [cid] = entries[0]
      quotas.set(cid, quotas.get(cid)! + 1)
      delta += 1
    }
  }
  for (const c of chapters) {
    const want = quotas.get(c.id) ?? 0
    if (want === 0) continue
    const pool = index.tasksByChapter.get(c.id) ?? []
    picks.push(...shuffle(pool).slice(0, Math.min(want, pool.length)))
  }
  return shuffle(picks)
}
