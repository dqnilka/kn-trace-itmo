import { useState } from 'react'
import { saveUser, userIdFromEmail } from '../state/user'

type Mode = 'login' | 'signup' | 'recovery' | 'recovery_sent'

/**
 * Auth-экран по диаграмме fsfr-user-flow v2 (узлы n2-n6f).
 *
 * MVP: фронт-only моки, без бэка. Эмулируем поведение ошибок и восстановления
 * пароля по «магическим» email для тестирования:
 *   • taken@test.com           → «email уже занят» при регистрации
 *   • wrong-pass@test.com      → «неверный пароль» при логине
 *   • notfound@test.com        → «аккаунт не найден» при логине
 *   • locked@test.com          → «слишком много попыток»
 *   • server-down@test.com     → «сервер недоступен»
 *
 * Любой другой валидный email — успешный вход/регистрация.
 */
export default function OnboardingScreen({
  onDone,
}: {
  onDone: () => void
}) {
  const [mode, setMode] = useState<Mode>('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const switchTo = (m: Mode) => {
    setMode(m)
    setErr(null)
  }

  const mockError = (e: string): string | null => {
    if (e === 'wrong-pass@test.com') return 'Неверный пароль'
    if (e === 'notfound@test.com') return 'Аккаунт не найден'
    if (e === 'locked@test.com') return 'Слишком много попыток. Попробуйте через 15 минут'
    if (e === 'server-down@test.com') return 'Сервер недоступен. Попробуйте позже'
    if (e === 'taken@test.com') return 'Этот email уже занят'
    return null
  }

  const submitAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    const cleanName = name.trim()
    const cleanEmail = email.trim().toLowerCase()
    setErr(null)
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setErr('Неверный формат email')
      return
    }
    if (mode === 'signup' && cleanName.length < 2) {
      setErr('Введите имя (минимум 2 символа)')
      return
    }
    if (mode !== 'recovery' && password.length < 4) {
      setErr('Пароль слишком короткий (минимум 4 символа)')
      return
    }
    setSubmitting(true)
    // имитация запроса
    await new Promise((r) => setTimeout(r, 450))
    setSubmitting(false)

    if (mode === 'recovery') {
      const me = mockError(cleanEmail)
      if (me === 'Аккаунт не найден' || me === 'Сервер недоступен. Попробуйте позже') {
        setErr(me)
        return
      }
      switchTo('recovery_sent')
      return
    }

    if (mode === 'login') {
      const me = mockError(cleanEmail)
      if (me) {
        setErr(me)
        return
      }
    }
    if (mode === 'signup') {
      const me = mockError(cleanEmail)
      if (me === 'Этот email уже занят' || me === 'Сервер недоступен. Попробуйте позже') {
        setErr(me)
        return
      }
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
            <div className="brand-sub">Экзамен ФСФР</div>
          </div>
        </div>

        {mode === 'recovery_sent' ? (
          <>
            <div style={{ fontSize: 48, marginTop: 12 }}>✉️</div>
            <h1 className="onboarding-title">Ссылка отправлена на email</h1>
            <p className="onboarding-sub">
              Мы отправили ссылку для восстановления пароля на{' '}
              <strong>{email}</strong>. Откройте письмо и следуйте инструкциям.
              Не пришло за 5 минут — проверьте папку «Спам».
            </p>
            <div className="actions-row" style={{ marginTop: 18 }}>
              <button className="pill pill-primary" onClick={() => switchTo('login')}>
                ← к входу
              </button>
            </div>
          </>
        ) : (
          <>
            <h1 className="onboarding-title">
              {mode === 'signup'
                ? 'Создайте аккаунт и начнём с входного теста'
                : mode === 'login'
                  ? 'Войдите, чтобы продолжить'
                  : 'Восстановление пароля'}
            </h1>
            <p className="onboarding-sub">
              {mode === 'recovery'
                ? 'Введите email — отправим ссылку для сброса пароля.'
                : '25 вопросов из реального банка экзамена помогут собрать карту знаний. Дальше — практика и теория ровно там, где есть пробелы.'}
            </p>

            {mode !== 'recovery' && (
              <div className="tabs onboarding-tabs">
                <button
                  className={mode === 'signup' ? 'active' : ''}
                  onClick={() => switchTo('signup')}
                  type="button"
                >
                  Регистрация
                </button>
                <button
                  className={mode === 'login' ? 'active' : ''}
                  onClick={() => switchTo('login')}
                  type="button"
                >
                  Вход
                </button>
              </div>
            )}

            <form className="form" onSubmit={submitAuth}>
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
                  autoFocus={mode !== 'signup'}
                />
              </label>
              {mode !== 'recovery' && (
                <label className="field">
                  <span>Пароль</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="минимум 4 символа"
                  />
                </label>
              )}
              {err && <div className="error">{err}</div>}
              <button
                className="pill pill-primary big"
                type="submit"
                disabled={submitting}
              >
                {submitting
                  ? 'Проверяем…'
                  : mode === 'signup'
                    ? 'Создать аккаунт →'
                    : mode === 'login'
                      ? 'Войти →'
                      : 'Отправить ссылку →'}
              </button>
              {mode === 'login' && (
                <button
                  type="button"
                  className="link-button"
                  style={{ alignSelf: 'flex-end', marginTop: -4 }}
                  onClick={() => switchTo('recovery')}
                >
                  Забыли пароль?
                </button>
              )}
              {mode === 'recovery' && (
                <button
                  type="button"
                  className="link-button"
                  style={{ alignSelf: 'flex-end', marginTop: -4 }}
                  onClick={() => switchTo('login')}
                >
                  ← вернуться к входу
                </button>
              )}
            </form>

            <p className="onboarding-foot">
              MVP: профиль хранится локально в браузере. Для теста ошибок используйте:
              <br />
              <code>wrong-pass@test.com</code>, <code>notfound@test.com</code>,{' '}
              <code>locked@test.com</code>, <code>server-down@test.com</code>,{' '}
              <code>taken@test.com</code>.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
