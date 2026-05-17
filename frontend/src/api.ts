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

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ''}`)
  }
  return res.json()
}

export const api = {
  health: () => fetchJson<Health>('/healthz'),
  // Multi-exam trainer plane
  exams: () => fetchJson<ExamListResponse>('/api/v1/exams'),
  examBank: (slug: string) => fetchJson<ExamBank>(`/api/v1/exams/${slug}/bank`),
  explain: (slug: string, task_id: number, picked_label: string | null) =>
    fetchJson<ExplainResponse>(`/api/v1/exams/${slug}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id, picked_label }),
    }),
  event: (
    slug: string,
    body: { user_id: number; task_id: number; picked_label: string | null; is_correct: boolean },
  ) =>
    fetchJson<EventResponse>(`/api/v1/exams/${slug}/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  recommend: (slug: string, body: { user_id: number; count?: number; target_p?: number }) =>
    fetchJson<RecommendResponse>(`/api/v1/exams/${slug}/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  mastery: (slug: string, user_id: number) =>
    fetchJson<MasteryResponse>(`/api/v1/exams/${slug}/mastery/${user_id}`),
  examTheme: (slug: string, code: string) =>
    fetchJson<ThemeArticleResponse>(
      `/api/v1/exams/${slug}/theme/${encodeURIComponent(code)}`,
    ),
}

// Admin API (no auth in MVP)
export const adminApi = {
  listExams: () => fetchJson<AdminExamsResponse>('/api/v1/admin/exams'),
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
