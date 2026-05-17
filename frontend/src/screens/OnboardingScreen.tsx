import { useState } from 'react'
import { saveUser, userIdFromEmail } from '../state/user'

export default function OnboardingScreen({
  onDone,
}: {
  onDone: () => void
}) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [mode, setMode] = useState<'login' | 'signup'>('signup')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanName = name.trim()
    const cleanEmail = email.trim().toLowerCase()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setErr('Неверный формат email')
      return
    }
    if (mode === 'signup' && cleanName.length < 2) {
      setErr('Введите имя (минимум 2 символа)')
      return
    }
    saveUser({
      id: userIdFromEmail(cleanEmail),
      name: cleanName || cleanEmail.split('@')[0],
      email: cleanEmail,
    })
    onDone()
  }

  return (
    <div className="screen onboarding-screen">
      <div className="onboarding-card">
        <div className="onboarding-brand">
          <div className="brand-mark">Ф</div>
          <div>
            <div className="brand-title">AI-подготовка</div>
            <div className="brand-sub">Базовый экзамен ФСФР</div>
          </div>
        </div>

        <h1 className="onboarding-title">
          {mode === 'signup'
            ? 'Создайте аккаунт и начнём с входного теста'
            : 'Войдите, чтобы продолжить'}
        </h1>
        <p className="onboarding-sub">
          25 вопросов из реального банка экзамена помогут собрать карту знаний.
          Дальше — практика и теория ровно там, где есть пробелы.
        </p>

        <div className="tabs onboarding-tabs">
          <button
            className={mode === 'signup' ? 'active' : ''}
            onClick={() => setMode('signup')}
          >
            Регистрация
          </button>
          <button
            className={mode === 'login' ? 'active' : ''}
            onClick={() => setMode('login')}
          >
            Вход
          </button>
        </div>

        <form className="form" onSubmit={submit}>
          {mode === 'signup' && (
            <label className="field">
              <span>Имя</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Иван"
                autoFocus
              />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoFocus={mode === 'login'}
            />
          </label>
          {err && <div className="error">{err}</div>}
          <button className="pill pill-primary big" type="submit">
            {mode === 'signup' ? 'Создать аккаунт →' : 'Войти →'}
          </button>
        </form>

        <p className="onboarding-foot">
          MVP: профиль хранится локально в браузере.
        </p>
      </div>
    </div>
  )
}
