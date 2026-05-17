import { useEffect, useMemo, useState } from 'react'
import HealthBadge from './components/HealthBadge'
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
import {
  clearUser,
  loadLastResults,
  loadUser,
  saveLastResults,
} from './state/user'
import type {
  BankEntranceResult,
  Health,
  Screen,
  UserState,
  WipReason,
} from './types'

function initialScreen(user: UserState | null, hasResults: boolean): Screen {
  if (!user) return 'onboarding'
  if (!hasResults) return 'entrance'
  return 'dashboard'
}

export default function App() {
  const [user, setUser] = useState<UserState | null>(() => loadUser())
  const [lastResults, setLastResults] = useState<BankEntranceResult | null>(() =>
    loadLastResults(),
  )
  const [screen, setScreen] = useState<Screen>(() =>
    initialScreen(loadUser(), loadLastResults() != null),
  )
  const [wipReason, setWipReason] = useState<WipReason>('other')
  const [practiceTheme, setPracticeTheme] = useState<string | null>(null)
  const [theoryTheme, setTheoryTheme] = useState<string | null>(null)
  const [examVariantId, setExamVariantId] = useState<number | null>(null)

  const [health, setHealth] = useState<Health | null>(null)
  const [healthErr, setHealthErr] = useState<string | null>(null)

  useEffect(() => {
    let stop = false
    const tick = async () => {
      try {
        const h = await api.health()
        if (!stop) {
          setHealth(h)
          setHealthErr(null)
        }
      } catch (e) {
        if (!stop) setHealthErr(e instanceof Error ? e.message : String(e))
      }
    }
    tick()
    const id = setInterval(tick, 15000)
    return () => {
      stop = true
      clearInterval(id)
    }
  }, [])

  const goOnboarded = () => {
    setUser(loadUser())
    setScreen('entrance')
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
    clearUser()
    setUser(null)
    setLastResults(null)
    setScreen('onboarding')
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

  let body: React.ReactNode = null
  if (screen === 'onboarding' || !user) {
    body = <OnboardingScreen onDone={goOnboarded} />
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
    body = <OnboardingScreen onDone={goOnboarded} />
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">Ф</div>
          <div>
            <h1>AI-подготовка к экзамену</h1>
            <div className="subtitle">Базовый ФСФР · адаптивный тренажёр</div>
          </div>
        </div>
        <div className="header-right">
          <a
            className="link-button"
            href="/admin"
            title="Управление экзаменами, пайплайн, граф"
          >
            ⚙ Админ-панель
          </a>
          <HealthBadge health={health} error={healthErr} />
        </div>
      </header>
      {body}
    </div>
  )
}
