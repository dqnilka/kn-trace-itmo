import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi } from '../api'
import type {
  AdminExam,
  AdminIngestOptions,
  AdminRun,
} from '../types'

type Status = AdminRun['status']

function statusClass(s: Status): string {
  if (s === 'success') return 'chip chip-ok'
  if (s === 'failed' || s === 'cancelled') return 'chip chip-err'
  if (s === 'running' || s === 'pending') return 'chip chip-running'
  return 'chip'
}

function fmtTime(ts: string | null): string {
  if (!ts) return '—'
  return ts.replace('T', ' ').replace('Z', '')
}

export default function AdminApp() {
  const [exams, setExams] = useState<AdminExam[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [activeSlug, setActiveSlug] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const r = await adminApi.listExams()
      setExams(r.exams)
      setErr(null)
      if (r.exams.length > 0 && !activeSlug) {
        setActiveSlug(r.exams[0].slug)
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [activeSlug])

  useEffect(() => {
    refresh()
  }, [refresh])

  const active = exams?.find((e) => e.slug === activeSlug) ?? null

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div className="brand">
          <div className="brand-mark">⚙</div>
          <div>
            <h1>Admin · K2-18</h1>
            <div className="subtitle">CRUD экзаменов, пайплайн, публикация</div>
          </div>
        </div>
        <div className="header-right">
          <a className="link-button" href="/" title="К пользовательскому фронту">
            ← к тренажёру
          </a>
          <button
            className="pill"
            onClick={async () => {
              await adminApi.reload()
              refresh()
            }}
          >
            обновить реестр
          </button>
          <button className="pill pill-primary" onClick={() => setShowCreate(true)}>
            + новый экзамен
          </button>
        </div>
      </header>

      {err && <div className="error">{err}</div>}

      <div className="admin-grid">
        <aside className="admin-list">
          {!exams && <div className="meta">загружаем…</div>}
          {exams && exams.length === 0 && (
            <div className="meta padded">
              Пока нет экзаменов. Нажмите «+ новый экзамен».
            </div>
          )}
          {exams?.map((e) => (
            <button
              key={e.slug}
              className={`exam-row ${activeSlug === e.slug ? 'active' : ''}`}
              onClick={() => setActiveSlug(e.slug)}
            >
              <div className="exam-row-title">{e.title}</div>
              <div className="exam-row-meta">
                <code>{e.slug}</code>
                <span className={`chip ${e.published ? 'chip-ok' : 'chip-muted'}`}>
                  {e.published ? 'опубликован' : 'черновик'}
                </span>
                {!e.has_bank && <span className="chip chip-err">нет банка</span>}
                {!e.has_theory && <span className="chip chip-muted">нет теории</span>}
              </div>
            </button>
          ))}
        </aside>
        <main className="admin-main">
          {active ? (
            <AdminExamPanel exam={active} onReload={refresh} />
          ) : (
            <div className="meta">Выбери экзамен слева.</div>
          )}
        </main>
      </div>

      {showCreate && (
        <CreateExamModal onClose={() => setShowCreate(false)} onCreated={refresh} />
      )}
    </div>
  )
}

function AdminExamPanel({
  exam,
  onReload,
}: {
  exam: AdminExam
  onReload: () => Promise<void>
}) {
  const [runs, setRuns] = useState<AdminRun[] | null>(null)
  const [activeRun, setActiveRun] = useState<string | null>(null)
  const [log, setLog] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [opts, setOpts] = useState<AdminIngestOptions>({
    top_k: 3,
    min_score: 0.35,
    limit: 0,
    llm_rerank: true,
    llm_top_k: 8,
    llm_batch: 8,
  })

  const loadRuns = useCallback(async () => {
    try {
      const r = await adminApi.runs(exam.slug)
      setRuns(r.runs)
      if (!activeRun && r.runs.length > 0) setActiveRun(r.runs[0].run_id)
    } catch (e) {
      console.warn(e)
    }
  }, [exam.slug, activeRun])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  // Auto-poll the active run if it's still going.
  useEffect(() => {
    if (!activeRun) return
    const stillLive = runs?.find(
      (r) => r.run_id === activeRun && (r.status === 'running' || r.status === 'pending'),
    )
    if (!stillLive) return
    const id = setInterval(async () => {
      try {
        const fresh = await adminApi.run(exam.slug, activeRun)
        setRuns((prev) =>
          prev?.map((p) => (p.run_id === fresh.run_id ? fresh : p)) ?? prev,
        )
        const lg = await adminApi.runLog(exam.slug, activeRun)
        setLog(lg.log)
        if (fresh.status !== 'running' && fresh.status !== 'pending') {
          clearInterval(id)
        }
      } catch (e) {
        console.warn(e)
      }
    }, 3000)
    return () => clearInterval(id)
  }, [activeRun, runs, exam.slug])

  // Load log when active run changes (snapshot).
  useEffect(() => {
    if (!activeRun) return
    adminApi.runLog(exam.slug, activeRun).then((r) => setLog(r.log))
  }, [activeRun, exam.slug])

  const startIngest = async () => {
    setBusy(true)
    try {
      const rec = await adminApi.ingest(exam.slug, opts)
      setActiveRun(rec.run_id)
      await loadRuns()
    } catch (e) {
      alert(`Ingest не запустился: ${e instanceof Error ? e.message : e}`)
    } finally {
      setBusy(false)
    }
  }

  const togglePublish = async () => {
    setBusy(true)
    try {
      if (exam.published) await adminApi.unpublish(exam.slug)
      else await adminApi.publish(exam.slug)
      await onReload()
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!confirm(`Удалить экзамен ${exam.slug}? Это снесёт всю папку!`)) return
    setBusy(true)
    try {
      await adminApi.deleteExam(exam.slug)
      await onReload()
    } finally {
      setBusy(false)
    }
  }

  const onUploadBank = async (file: File) => {
    setBusy(true)
    try {
      await adminApi.uploadBank(exam.slug, file)
      await onReload()
    } catch (e) {
      alert(`Bank upload failed: ${e instanceof Error ? e.message : e}`)
    } finally {
      setBusy(false)
    }
  }

  const onUploadTheory = async (file: File) => {
    setBusy(true)
    try {
      await adminApi.uploadTheory(exam.slug, file)
      await onReload()
    } catch (e) {
      alert(`Theory upload failed: ${e instanceof Error ? e.message : e}`)
    } finally {
      setBusy(false)
    }
  }

  const cancelActive = async () => {
    if (!activeRun) return
    await adminApi.cancelRun(exam.slug, activeRun)
    await loadRuns()
  }

  return (
    <div>
      <div className="admin-section">
        <div className="admin-section-head">
          <div>
            <div className="admin-eyebrow">{exam.slug}</div>
            <h2>{exam.title}</h2>
            <div className="meta">{exam.subtitle}</div>
          </div>
          <div className="header-actions">
            <a
              className="pill"
              href={`/api/v1/exams/${exam.slug}/viewer`}
              target="_blank"
              rel="noreferrer noopener"
              title="k2-18 viewer (новая вкладка)"
            >
              📊 граф
            </a>
            <a
              className="link-button"
              href={`/api/v1/exams/${exam.slug}/graph/summary`}
              target="_blank"
              rel="noreferrer noopener"
            >
              JSON summary
            </a>
            <button className="pill" disabled={busy} onClick={togglePublish}>
              {exam.published ? 'снять с публикации' : 'опубликовать'}
            </button>
            <button className="pill pill-err" disabled={busy} onClick={remove}>
              удалить
            </button>
          </div>
        </div>
      </div>

      <div className="admin-section">
        <div className="admin-section-title">Артефакты</div>
        <div className="admin-uploads">
          <UploadField
            label="Bank (.xlsx)"
            accept=".xlsx,.xls"
            ok={exam.has_bank}
            disabled={busy}
            onPick={onUploadBank}
            hint="После загрузки выполнится convert_bank → bank.json"
          />
          <UploadField
            label="Theory (.md)"
            accept=".md,.markdown"
            ok={exam.has_theory}
            disabled={busy}
            onPick={onUploadTheory}
            hint="Markdown учебника, используется в RAG-разборах"
          />
        </div>
      </div>

      <div className="admin-section">
        <div className="admin-section-title">Запуск пайплайна</div>
        <div className="admin-ingest-row">
          <label className="field inline">
            <span>top-K</span>
            <input
              type="number"
              value={opts.top_k}
              min={1}
              max={10}
              onChange={(e) =>
                setOpts((p) => ({ ...p, top_k: parseInt(e.target.value || '3', 10) }))
              }
            />
          </label>
          <label className="field inline">
            <span>min-score</span>
            <input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={opts.min_score}
              onChange={(e) =>
                setOpts((p) => ({ ...p, min_score: parseFloat(e.target.value || '0.35') }))
              }
            />
          </label>
          <label className="field inline">
            <span>limit (0 = весь банк)</span>
            <input
              type="number"
              value={opts.limit}
              min={0}
              onChange={(e) =>
                setOpts((p) => ({ ...p, limit: parseInt(e.target.value || '0', 10) }))
              }
            />
            {(opts.limit ?? 0) > 0 && (
              <span className="meta" style={{ color: 'var(--err)' }}>
                ⚠ перетрёт текущий graph.json
              </span>
            )}
          </label>
          <label className="field inline checkbox">
            <input
              type="checkbox"
              checked={!!opts.llm_rerank}
              onChange={(e) => setOpts((p) => ({ ...p, llm_rerank: e.target.checked }))}
            />
            <span>LLM rerank (медленнее, точнее)</span>
          </label>
          {opts.llm_rerank && (
            <>
              <label className="field inline">
                <span>llm top-K</span>
                <input
                  type="number"
                  value={opts.llm_top_k}
                  onChange={(e) =>
                    setOpts((p) => ({ ...p, llm_top_k: parseInt(e.target.value || '8', 10) }))
                  }
                />
              </label>
              <label className="field inline">
                <span>llm batch</span>
                <input
                  type="number"
                  value={opts.llm_batch}
                  onChange={(e) =>
                    setOpts((p) => ({ ...p, llm_batch: parseInt(e.target.value || '8', 10) }))
                  }
                />
              </label>
            </>
          )}
          <button
            className="pill pill-primary"
            disabled={!exam.has_bank || busy}
            onClick={startIngest}
          >
            Запустить ingest →
          </button>
        </div>
      </div>

      <div className="admin-section">
        <div className="admin-section-title">История запусков</div>
        <div className="admin-runs">
          <ul className="admin-runs-list">
            {(runs ?? []).map((r) => (
              <li
                key={r.run_id}
                className={activeRun === r.run_id ? 'active' : ''}
                onClick={() => setActiveRun(r.run_id)}
              >
                <span className={statusClass(r.status)}>{r.status}</span>
                <code>{r.run_id}</code>
                <span className="meta">{fmtTime(r.started_at)}</span>
                <span className="meta">{r.notes}</span>
              </li>
            ))}
            {runs && runs.length === 0 && <li className="meta">пусто</li>}
          </ul>
          {activeRun && (
            <div className="admin-run-log">
              <div className="admin-section-head" style={{ marginBottom: 6 }}>
                <code>{activeRun}</code>
                {runs?.find((r) => r.run_id === activeRun)?.status === 'running' && (
                  <button className="pill pill-err" onClick={cancelActive}>
                    отменить
                  </button>
                )}
              </div>
              <pre className="log-pre">{log || '(лог пуст)'}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function UploadField({
  label,
  accept,
  ok,
  disabled,
  onPick,
  hint,
}: {
  label: string
  accept: string
  ok: boolean
  disabled?: boolean
  onPick: (f: File) => void
  hint?: string
}) {
  return (
    <div className={`upload-card ${ok ? 'ok' : 'pending'}`}>
      <div className="upload-head">
        <span className="upload-label">{label}</span>
        <span className={`chip ${ok ? 'chip-ok' : 'chip-muted'}`}>
          {ok ? 'есть' : 'нет'}
        </span>
      </div>
      <input
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onPick(f)
        }}
      />
      {hint && <div className="meta">{hint}</div>}
    </div>
  )
}

function CreateExamModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [slug, setSlug] = useState('')
  const [title, setTitle] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await adminApi.createExam({ slug: slug.trim(), title: title.trim(), subtitle })
      await onCreated()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Новый экзамен</h2>
        <form className="form" onSubmit={submit}>
          <label className="field">
            <span>slug (латиница, цифры, -_)</span>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="cfa-level-1"
              autoFocus
            />
          </label>
          <label className="field">
            <span>Название</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="CFA Level I"
            />
          </label>
          <label className="field">
            <span>Подзаголовок (опц.)</span>
            <input
              type="text"
              value={subtitle}
              onChange={(e) => setSubtitle(e.target.value)}
            />
          </label>
          {err && <div className="error">{err}</div>}
          <div className="actions-row">
            <button type="submit" className="pill pill-primary" disabled={busy}>
              Создать
            </button>
            <button type="button" className="pill" onClick={onClose}>
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
