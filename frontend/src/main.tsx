import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AdminApp from './admin/AdminApp'
import KitScreen from './screens/KitScreen'
import ErrorBoundary from './components/ErrorBoundary'
import './styles.css'

// Lightweight in-app routing:
//   /admin (or ?admin=1) → admin shell
//   ?kit=1               → design-system showcase
//   anything else        → user-facing trainer.
const params =
  typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams()
const isAdminRoute =
  typeof window !== 'undefined' &&
  (window.location.pathname.startsWith('/admin') || params.has('admin'))
const isKitRoute = params.has('kit')

function Root() {
  if (isKitRoute) return <KitScreen />
  if (isAdminRoute) return <AdminApp />
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Root />
    </ErrorBoundary>
  </React.StrictMode>,
)
