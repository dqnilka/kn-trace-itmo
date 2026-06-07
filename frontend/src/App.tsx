import { useEffect, useState } from 'react'
import BrandWordmark from './components/BrandWordmark'
import AuthScreen from './screens/AuthScreen'
import OnboardingScreen from './screens/OnboardingScreen'
import EntranceTestScreen from './screens/EntranceTestScreen'
import ResultsScreen from './screens/ResultsScreen'
import DashboardScreen from './screens/DashboardScreen'
import PracticeScreen from './screens/PracticeScreen'
import AdaptiveSessionScreen from './screens/AdaptiveSessionScreen'
import LearningPathScreen from './screens/LearningPathScreen'
import TheoryScreen from './screens/TheoryScreen'
import ExamVariantScreen from './screens/ExamVariantScreen'
import WipScreen from './screens/WipScreen'
import { api } from './api'
import { clearToken, decodeUser, getToken } from './state/auth'
import { ACTIVE_EXAM_SLUG } from './state/bank'
import { loadMastery, saveMastery } from './state/mastery'
import {
  clearUser,
  loadLastResults,
  loadUser,
  saveLastResults,
  saveUser,
} from './state/user'
import type {
  AuthUser,
  BankEntranceResult,
  MasteryStore,
  Screen,
  UserState,
  WipReason,
} from './types'

function initialScreen(): Screen {
  // Возвращающийся пользователь (есть результаты входного ИЛИ накопленный
  // прогресс) → Главная. Иначе — входной тест.
  const started =
    loadLastResults() != null || Object.keys(loadMastery()).length > 0
  return started ? 'dashboard' : 'entrance'
}

/** Hydrate localStorage mastery from the server (server is source of truth). */
async function hydrateMastery(): Promise<void> {
  try {
    const res = await api.myMastery(ACTIVE_EXAM_SLUG)
    const local = loadMastery()
    const merged: MasteryStore = { ...local }
    const now = new Date().toISOString()
    for (const [code, st] of Object.entries(res.themes)) {
      const prev = merged[code]
      // Keep whichever side has more answers — avoids losing unsynced local.
      if (!prev || st.asked >= prev.asked) {
        merged[code] = { asked: st.asked, correct: st.correct, last_practiced: now }
      }
    }
    saveMastery(merged)
  } catch {
    // best-effort — offline / no DB → keep local
  }
}

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => decodeUser(getToken()) != null)
  const [user, setUser] = useState<UserState | null>(() => {
    const au = decodeUser(getToken())
    if (!au) return null
    return (
      loadUser() ?? {
        id: au.id,
        name: au.email.split('@')[0],
        email: au.email,
        is_admin: au.is_admin,
      }
    )
  })
  const [lastResults, setLastResults] = useState<BankEntranceResult | null>(() =>
    loadLastResults(),
  )
  const [screen, setScreen] = useState<Screen>(() => initialScreen())
  const [wipReason, setWipReason] = useState<WipReason>('other')
  const [practiceTheme, setPracticeTheme] = useState<string | null>(null)
  const [theoryTheme, setTheoryTheme] = useState<string | null>(null)
  const [examVariantId, setExamVariantId] = useState<number | null>(null)

  // Sync local mastery up to the server whenever we land on the dashboard
  // (after entrance / a lesson / practice). Absolute upsert → idempotent.
  useEffect(() => {
    if (!authed || screen !== 'dashboard') return
    const store = loadMastery()
    const themes: Record<string, { asked: number; correct: number }> = {}
    for (const [code, m] of Object.entries(store)) {
      themes[code] = { asked: m.asked, correct: m.correct }
    }
    api.putMyMastery(ACTIVE_EXAM_SLUG, themes).catch(() => {})
  }, [authed, screen])

  const onAuthed = (au: AuthUser) => {
    const u: UserState = {
      id: au.id,
      name: au.display_name || au.email.split('@')[0],
      email: au.email,
      is_admin: au.is_admin,
    }
    saveUser(u)
    setUser(u)
    setAuthed(true)
    // Экран выбираем СИНХРОННО, чтобы медленная гидрация не перебросила
    // пользователя позже (раньше это выкидывало из начатого входного теста).
    const started =
      loadLastResults() != null || Object.keys(loadMastery()).length > 0
    setScreen(started ? 'dashboard' : 'onboarding')
    // Подтянуть серверный прогресс в фоне — без смены экрана.
    void hydrateMastery()
  }

  const onEntranceDone = (summary: BankEntranceResult) => {
    saveLastResults(summary)
    setLastResults(summary)
    setScreen('results')
  }

  const onEntranceSkip = () => {
    // No results recorded — user lands on dashboard with the warning banner.
    setScreen('dashboard')
  }

  const onLogout = () => {
    clearToken()
    clearUser()
    setUser(null)
    setAuthed(false)
    setLastResults(null)
  }

  const goWip = (r: WipReason) => {
    setWipReason(r)
    setScreen('wip')
  }

  const goPractice = (themeCode: string) => {
    setPracticeTheme(themeCode)
    setScreen('practice')
  }

  const goTheory = (themeCode: string) => {
    setTheoryTheme(themeCode)
    setScreen('theory')
  }

  // Главный путь обучения — миксует теорию + практику по слабым темам.
  const goAdaptive = () => setScreen('learning')

  const goExam = (variantId: number) => {
    setExamVariantId(variantId)
    setScreen('exam')
  }

  // Auth gate — без валидного токена показываем вход/регистрацию.
  if (!authed || !user) {
    return (
      <div className="app">
        <header className="app-header">
          <div className="brand">
            <BrandWordmark />
          </div>
        </header>
        <AuthScreen onAuthed={onAuthed} />
      </div>
    )
  }

  let body: React.ReactNode = null
  if (screen === 'onboarding') {
    body = <OnboardingScreen onDone={() => setScreen('entrance')} />
  } else if (screen === 'entrance') {
    body = (
      <EntranceTestScreen
        user={user}
        onDone={onEntranceDone}
        onBack={() => setScreen(lastResults ? 'dashboard' : 'onboarding')}
        onSkip={onEntranceSkip}
      />
    )
  } else if (screen === 'results' && lastResults) {
    body = (
      <ResultsScreen
        result={lastResults}
        onContinue={() => setScreen('dashboard')}
      />
    )
  } else if (screen === 'dashboard') {
    body = (
      <DashboardScreen
        user={user}
        onAdaptive={goAdaptive}
        onPractice={goPractice}
        onTheory={goTheory}
        onExamVariant={goExam}
        onLogout={onLogout}
        onRetakeEntrance={() => setScreen('entrance')}
        hasEntranceResults={lastResults != null}
      />
    )
  } else if (screen === 'theory' && theoryTheme) {
    body = (
      <TheoryScreen
        themeCode={theoryTheme}
        onBack={() => setScreen('dashboard')}
        onPractice={(code) => {
          setPracticeTheme(code)
          setScreen('practice')
        }}
      />
    )
  } else if (screen === 'practice' && practiceTheme) {
    body = (
      <PracticeScreen
        user={user}
        themeCode={practiceTheme}
        onBack={() => setScreen('dashboard')}
        onPickAnotherTheme={() => setScreen('dashboard')}
      />
    )
  } else if (screen === 'adaptive') {
    body = (
      <AdaptiveSessionScreen
        onBack={() => setScreen('dashboard')}
        onRestart={() => setScreen('adaptive')}
      />
    )
  } else if (screen === 'learning') {
    body = (
      <LearningPathScreen
        onBack={() => setScreen('dashboard')}
        onRestart={() => setScreen('learning')}
      />
    )
  } else if (screen === 'exam' && examVariantId != null) {
    body = (
      <ExamVariantScreen
        variantId={examVariantId}
        onBack={() => setScreen('dashboard')}
      />
    )
  } else if (screen === 'wip') {
    body = (
      <WipScreen
        reason={wipReason}
        onBack={() => setScreen(lastResults ? 'dashboard' : 'entrance')}
      />
    )
  } else {
    body = (
      <DashboardScreen
        user={user}
        onAdaptive={goAdaptive}
        onPractice={goPractice}
        onTheory={goTheory}
        onExamVariant={goExam}
        onLogout={onLogout}
        onRetakeEntrance={() => setScreen('entrance')}
        hasEntranceResults={lastResults != null}
      />
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <BrandWordmark />
        </div>
        <div className="header-right">
          {user?.is_admin && (
            <a
              className="link-button"
              href="/admin"
              title="Управление экзаменами, пайплайн, граф"
            >
              Админ-панель
            </a>
          )}
        </div>
      </header>
      {body}
    </div>
  )
}
