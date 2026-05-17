import { useEffect, useState } from 'react'
import ErrorBoundary from './components/ErrorBoundary'
import HealthBadge from './components/HealthBadge'
import PostExamModal, { markExamTaken } from './components/PostExamModal'
import OnboardingScreen from './screens/OnboardingScreen'
import ExamSeriesScreen, { loadSeries } from './screens/ExamSeriesScreen'
import EntranceTestScreen from './screens/EntranceTestScreen'
import ResultsScreen from './screens/ResultsScreen'
import DashboardScreen from './screens/DashboardScreen'
import PracticeScreen from './screens/PracticeScreen'
import AdaptiveSessionScreen from './screens/AdaptiveSessionScreen'
import LearningPathScreen from './screens/LearningPathScreen'
import TheoryScreen from './screens/TheoryScreen'
import ExamVariantScreen from './screens/ExamVariantScreen'
import MockOutcomeScreen, { type MockOutcomeMode } from './screens/MockOutcomeScreen'
import FinalStretchScreen from './screens/FinalStretchScreen'
import RealExamPrepScreen from './screens/RealExamPrepScreen'
import WipScreen from './screens/WipScreen'
import { api, isAbortError } from './api'
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
  if (!loadSeries()) return 'series'
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
  const [mockOutcome, setMockOutcome] = useState<{
    mode: MockOutcomeMode
    pct: number
  } | null>(null)
  const [forcePostExam, setForcePostExam] = useState(false)

  const [health, setHealth] = useState<Health | null>(null)
  const [healthErr, setHealthErr] = useState<string | null>(null)

  useEffect(() => {
    let stop = false
    let lastCtrl: AbortController | null = null
    const tick = async () => {
      // Отменяем предыдущий health-запрос, если он ещё в полёте — на медленной
      // сети они не должны накапливаться и спамить /healthz.
      lastCtrl?.abort()
      const ctrl = new AbortController()
      lastCtrl = ctrl
      try {
        const h = await api.health({ signal: ctrl.signal, timeoutMs: 8_000 })
        if (!stop && !ctrl.signal.aborted) {
          setHealth(h)
          setHealthErr(null)
        }
      } catch (e) {
        if (stop || ctrl.signal.aborted || isAbortError(e)) return
        setHealthErr(e instanceof Error ? e.message : String(e))
      }
    }
    tick()
    const id = setInterval(tick, 15000)
    return () => {
      stop = true
      clearInterval(id)
      lastCtrl?.abort()
    }
  }, [])

  const goOnboarded = () => {
    setUser(loadUser())
    setScreen(loadSeries() ? 'entrance' : 'series')
  }

  const onSeriesPicked = () => setScreen('entrance')

  const onEntranceDone = (summary: BankEntranceResult) => {
    saveLastResults(summary)
    setLastResults(summary)
    setScreen('results')
  }

  const onEntranceSkip = () => {
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

  const goAdaptive = () => setScreen('learning')

  const goExam = (variantId: number) => {
    setExamVariantId(variantId)
    setScreen('exam')
  }

  const onMockOutcome = (passed: boolean, pct: number) => {
    setMockOutcome({ mode: passed ? 'success' : 'fail', pct })
    setScreen('mock-outcome')
  }

  let body: React.ReactNode = null
  if (screen === 'onboarding' || !user) {
    body = <OnboardingScreen onDone={goOnboarded} />
  } else if (screen === 'series') {
    body = <ExamSeriesScreen onDone={onSeriesPicked} />
  } else if (screen === 'entrance') {
    body = (
      <EntranceTestScreen
        user={user}
        onDone={onEntranceDone}
        onBack={() => setScreen(lastResults ? 'dashboard' : 'series')}
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
        onFinalStretch={() => setScreen('final-stretch')}
        onRealExam={() => setScreen('real-exam')}
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
        onOpenTheory={goTheory}
      />
    )
  } else if (screen === 'adaptive') {
    body = (
      <AdaptiveSessionScreen
        onBack={() => setScreen('dashboard')}
        onRestart={() => setScreen('adaptive')}
        onOpenTheory={goTheory}
      />
    )
  } else if (screen === 'learning') {
    body = (
      <LearningPathScreen
        onBack={() => setScreen('dashboard')}
        onRestart={() => setScreen('learning')}
        onOpenTheory={goTheory}
      />
    )
  } else if (screen === 'exam' && examVariantId != null) {
    body = (
      <ExamVariantScreen
        variantId={examVariantId}
        onBack={() => setScreen('dashboard')}
        onOutcome={onMockOutcome}
      />
    )
  } else if (screen === 'mock-outcome' && mockOutcome) {
    body = (
      <MockOutcomeScreen
        mode={mockOutcome.mode}
        pct={mockOutcome.pct}
        onBack={() => setScreen('dashboard')}
        onPracticeWeak={() => setScreen('learning')}
        onScheduleConfirm={() => setScreen('dashboard')}
        onFinalStretch={() => setScreen('final-stretch')}
      />
    )
  } else if (screen === 'final-stretch') {
    body = (
      <FinalStretchScreen
        onBack={() => setScreen('dashboard')}
        onReady={() => setScreen('real-exam')}
        onRealExam={() => setScreen('real-exam')}
      />
    )
  } else if (screen === 'real-exam') {
    body = (
      <RealExamPrepScreen
        onBack={() => setScreen('dashboard')}
        onExamDone={() => {
          markExamTaken()
          setForcePostExam(true)
          setScreen('dashboard')
        }}
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
            <div className="subtitle">
              ФСФР · адаптивный тренажёр
            </div>
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
      {/* ErrorBoundary только вокруг тела — хедер должен оставаться видимым,
          даже если экран упал, чтобы пользователь мог хотя бы нажать «выход». */}
      <ErrorBoundary>{body}</ErrorBoundary>

      {/* Post-exam modal (24 ч после реального экзамена) */}
      {(screen === 'dashboard' || forcePostExam) && (
        <PostExamModal
          force={forcePostExam}
          onClose={() => setForcePostExam(false)}
          onRetry={() => {
            setForcePostExam(false)
            setScreen('learning')
          }}
        />
      )}
    </div>
  )
}
