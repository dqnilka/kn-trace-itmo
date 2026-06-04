import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AdminApp from './admin/AdminApp'
import ErrorBoundary from './components/ErrorBoundary'
import './styles.css'

// Lightweight in-app routing: /admin (or ?admin=1) → admin shell, anything
// else → user-facing trainer.
const isAdminRoute =
  typeof window !== 'undefined' &&
  (window.location.pathname.startsWith('/admin') ||
    new URLSearchParams(window.location.search).has('admin'))

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>{isAdminRoute ? <AdminApp /> : <App />}</ErrorBoundary>
  </React.StrictMode>,
)
