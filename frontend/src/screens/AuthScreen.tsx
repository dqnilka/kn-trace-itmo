import { useState } from 'react'
import { api, isAbortError } from '../api'
import { setToken } from '../state/auth'
import type { AuthUser } from '../types'

/**
 * Вход / регистрация. Один экран с переключателем режима.
 * При успехе сохраняет JWT и отдаёт пользователя наверх (App).
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
        // Бэкенд отдаёт «409 …: {"detail":"…"}» — вытащим человеко-читаемое.
        const m = msg.match(/"detail":"([^"]+)"/)
        setErr(m ? m[1] : msg)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="screen">
      <div className="screen-body narrow centered">
        <div className="trophy" aria-hidden="true">
          🎯
        </div>
        <h1 className="screen-title">
          {mode === 'login' ? 'Вход' : 'Регистрация'}
        </h1>
        <p className="screen-subtitle">
          Прогресс по темам сохраняется в твоём аккаунте — между устройствами и
          сессиями.
        </p>

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
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
          <input
            className="input"
            type="password"
            placeholder="пароль (от 6 символов)"
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

        <button
          className="link-button"
          style={{ marginTop: 14 }}
          onClick={() => {
            setErr(null)
            setMode((m) => (m === 'login' ? 'register' : 'login'))
          }}
        >
          {mode === 'login'
            ? 'Нет аккаунта? Зарегистрироваться'
            : 'Уже есть аккаунт? Войти'}
        </button>
      </div>
    </div>
  )
}
