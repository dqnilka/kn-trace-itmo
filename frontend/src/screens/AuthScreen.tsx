import { useState } from 'react'
import { api, isAbortError } from '../api'
import Logo from '../components/Logo'
import { setToken } from '../state/auth'
import type { AuthUser } from '../types'

/**
 * Вход / регистрация. Сдержанная центрированная карточка с переключателем-
 * табами. При успехе сохраняет JWT и отдаёт пользователя наверх (App).
 */
export default function AuthScreen({
  onAuthed,
}: {
  onAuthed: (user: AuthUser) => void
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    const mail = email.trim().toLowerCase()
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail)) {
      setErr('Введите корректный email')
      return
    }
    if (password.length < 6) {
      setErr('Пароль — минимум 6 символов')
      return
    }
    setBusy(true)
    try {
      const res =
        mode === 'register'
          ? await api.register({ email: mail, password, display_name: name.trim() || undefined })
          : await api.login({ email: mail, password })
      setToken(res.token)
      onAuthed(res.user)
    } catch (e) {
      if (!isAbortError(e)) {
        const msg = e instanceof Error ? e.message : String(e)
        const m = msg.match(/"detail":"([^"]+)"/)
        setErr(m ? m[1] : msg)
      }
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (m: 'login' | 'register') => {
    setErr(null)
    setMode(m)
  }

  return (
    <div className="screen">
      <div className="screen-body centered">
        <div className="auth-card">
          <div className="auth-logo">
            <Logo size={52} />
          </div>
          <h1 className="screen-title" style={{ textAlign: 'center', marginBottom: 4 }}>
            ФинТренажёр
          </h1>
          <p
            className="screen-subtitle"
            style={{ textAlign: 'center', marginTop: 0 }}
          >
            Подготовка к экзамену ФСФР. Прогресс сохраняется в аккаунте.
          </p>

          <div className="auth-tabs" role="tablist">
            <button
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => switchMode('login')}
              type="button"
            >
              Вход
            </button>
            <button
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => switchMode('register')}
              type="button"
            >
              Регистрация
            </button>
          </div>

          <form className="auth-form" onSubmit={submit}>
            {mode === 'register' && (
              <input
                className="input"
                type="text"
                placeholder="Имя (необязательно)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            )}
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
            <input
              className="input"
              type="password"
              placeholder="Пароль (от 6 символов)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
            />
            {err && <div className="error">{err}</div>}
            <button className="pill pill-primary big" type="submit" disabled={busy}>
              {busy ? '…' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
