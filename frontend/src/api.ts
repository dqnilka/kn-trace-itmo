import type {
  AdminExamsResponse,
  AdminIngestOptions,
  AdminRun,
  AdminRunsResponse,
  EventResponse,
  ExamListResponse,
  ExamBank,
  ExplainResponse,
  Health,
  MasteryResponse,
  RecommendResponse,
  ThemeArticleResponse,
} from './types'

/**
 * Опции запроса: можно передавать AbortSignal — обязательно при автофетче в
 * useEffect, иначе мы рискуем
 *   а) перезаписать state ответом от уже unmount-нутого компонента,
 *   б) на ExplainBlock сжечь лишние LLM-токены на гонке навигации.
 *
 * Дефолтный таймаут 90 секунд: дольше LLM не должна жевать; если жуёт —
 * пользователь и так заскучает.
 */
export type FetchOpts = { signal?: AbortSignal; timeoutMs?: number }

const DEFAULT_TIMEOUT_MS = 90_000

function withTimeout(opts: FetchOpts | undefined): AbortSignal | undefined {
  const ms = opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  if (opts?.signal && ms > 0) {
    // Композиция: либо пользовательский abort, либо таймаут.
    const ctrl = new AbortController()
    const onAbort = () => ctrl.abort(opts.signal!.reason)
    opts.signal.addEventListener('abort', onAbort, { once: true })
    const tid = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')), ms)
    ctrl.signal.addEventListener('abort', () => {
      clearTimeout(tid)
      opts.signal!.removeEventListener('abort', onAbort)
    })
    return ctrl.signal
  }
  if (opts?.signal) return opts.signal
  if (ms > 0) return AbortSignal.timeout(ms)
  return undefined
}

async function fetchJson<T>(
  url: string,
  init?: RequestInit,
  opts?: FetchOpts,
): Promise<T> {
  const signal = withTimeout(opts)
  const res = await fetch(url, { ...init, signal })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ''}`)
  }
  return res.json()
}

export const api = {
  health: (opts?: FetchOpts) => fetchJson<Health>('/healthz', undefined, opts),
  // Multi-exam trainer plane
  exams: (opts?: FetchOpts) =>
    fetchJson<ExamListResponse>('/api/v1/exams', undefined, opts),
  examBank: (slug: string, opts?: FetchOpts) =>
    fetchJson<ExamBank>(`/api/v1/exams/${slug}/bank`, undefined, opts),
  explain: (
    slug: string,
    task_id: number,
    picked_label: string | null,
    opts?: FetchOpts,
  ) =>
    fetchJson<ExplainResponse>(
      `/api/v1/exams/${slug}/explain`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id, picked_label }),
      },
      opts,
    ),
  event: (
    slug: string,
    body: { user_id: number; task_id: number; picked_label: string | null; is_correct: boolean },
    opts?: FetchOpts,
  ) =>
    fetchJson<EventResponse>(
      `/api/v1/exams/${slug}/event`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
      opts,
    ),
  recommend: (
    slug: string,
    body: { user_id: number; count?: number; target_p?: number },
    opts?: FetchOpts,
  ) =>
    fetchJson<RecommendResponse>(
      `/api/v1/exams/${slug}/recommend`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
      opts,
    ),
  mastery: (slug: string, user_id: number, opts?: FetchOpts) =>
    fetchJson<MasteryResponse>(
      `/api/v1/exams/${slug}/mastery/${user_id}`,
      undefined,
      opts,
    ),
  examTheme: (slug: string, code: string, opts?: FetchOpts) =>
    fetchJson<ThemeArticleResponse>(
      `/api/v1/exams/${slug}/theme/${encodeURIComponent(code)}`,
      undefined,
      opts,
    ),
}

// Admin API (no auth in MVP)
export const adminApi = {
  listExams: (opts?: FetchOpts) =>
    fetchJson<AdminExamsResponse>('/api/v1/admin/exams', undefined, opts),
  createExam: (body: { slug: string; title: string; subtitle?: string }) =>
    fetchJson<{ slug: string; title: string; published: boolean }>(
      '/api/v1/admin/exams',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    ),
  uploadBank: async (slug: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`/api/v1/admin/exams/${slug}/bank`, {
      method: 'POST',
      body: fd,
    })
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
    return res.json()
  },
  uploadTheory: async (slug: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`/api/v1/admin/exams/${slug}/theory`, {
      method: 'POST',
      body: fd,
    })
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
    return res.json()
  },
  ingest: (slug: string, opts: AdminIngestOptions = {}) =>
    fetchJson<AdminRun>(`/api/v1/admin/exams/${slug}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        top_k: opts.top_k ?? 3,
        min_score: opts.min_score ?? 0.35,
        limit: opts.limit ?? 0,
        llm_rerank: opts.llm_rerank ?? false,
        llm_top_k: opts.llm_top_k ?? 8,
        llm_batch: opts.llm_batch ?? 8,
      }),
    }),
  runs: (slug: string) =>
    fetchJson<AdminRunsResponse>(`/api/v1/admin/exams/${slug}/runs`),
  run: (slug: string, run_id: string) =>
    fetchJson<AdminRun>(`/api/v1/admin/exams/${slug}/runs/${run_id}`),
  runLog: (slug: string, run_id: string, tail: number = 400) =>
    fetchJson<{ run_id: string; log: string }>(
      `/api/v1/admin/exams/${slug}/runs/${run_id}/log?tail=${tail}`,
    ),
  cancelRun: (slug: string, run_id: string) =>
    fetchJson<{ ok: boolean }>(
      `/api/v1/admin/exams/${slug}/runs/${run_id}/cancel`,
      { method: 'POST' },
    ),
  publish: (slug: string) =>
    fetchJson<{ ok: boolean }>(`/api/v1/admin/exams/${slug}/publish`, {
      method: 'POST',
    }),
  unpublish: (slug: string) =>
    fetchJson<{ ok: boolean }>(`/api/v1/admin/exams/${slug}/unpublish`, {
      method: 'POST',
    }),
  deleteExam: (slug: string) =>
    fetchJson<{ ok: boolean }>(`/api/v1/admin/exams/${slug}`, {
      method: 'DELETE',
    }),
  reload: () =>
    fetchJson<{ ok: boolean; exams: string[] }>('/api/v1/admin/reload', {
      method: 'POST',
    }),
}

/**
 * Хелпер: считать ли ошибку из fetch результатом отмены (abort/timeout)?
 * Используется в `.catch()` поверх api-вызовов чтобы не показывать "ошибку"
 * пользователю при штатном размонтировании компонента.
 */
export function isAbortError(e: unknown): boolean {
  if (e instanceof DOMException && (e.name === 'AbortError' || e.name === 'TimeoutError')) {
    return true
  }
  // fetch иногда оборачивает ошибку — проверим имя в тексте
  const msg = e instanceof Error ? e.message : String(e)
  return /aborted|abortError|timeout/i.test(msg) && !msg.includes('NetworkError')
}
