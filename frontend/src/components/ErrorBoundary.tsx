import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * Корневой ErrorBoundary. Ловит любые исключения в render-фазе детей,
 * показывает дружелюбный экран ошибки вместо белого, и даёт «перезагрузить».
 *
 * Используется как обёртка над `body` в App.tsx и `AdminApp` в main.tsx.
 *
 * В продакшене сюда же место для отправки в Sentry / собственный лог.
 */

type State = { err: Error | null }

export default class ErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { err: null }

  static getDerivedStateFromError(err: Error): State {
    return { err }
  }

  componentDidCatch(err: Error, info: ErrorInfo): void {
    // Лог в консоль; в проде заменить на отправку в трекер.
    // eslint-disable-next-line no-console
    console.error('UI crashed:', err, info.componentStack)
  }

  private reset = () => {
    this.setState({ err: null })
  }

  render() {
    if (this.state.err) {
      return (
        <div className="screen">
          <div className="screen-body narrow centered">
            <div className="trophy" aria-hidden="true">
              
            </div>
            <h1 className="screen-title">Что-то сломалось</h1>
            <p className="screen-subtitle">
              UI неожиданно поломался. Попробуй перезагрузить страницу. Если
              повторяется — открой DevTools → Console, скопируй ошибку и
              скинь нам в issue.
            </p>
            <details className="error" style={{ textAlign: 'left' }}>
              <summary>Подробности ошибки</summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
                {this.state.err.name}: {this.state.err.message}
                {'\n\n'}
                {this.state.err.stack}
              </pre>
            </details>
            <div className="actions-row" style={{ marginTop: 18 }}>
              <button
                className="pill pill-primary big"
                onClick={() => location.reload()}
              >
                Перезагрузить
              </button>
              <button className="pill" onClick={this.reset}>
                Попробовать ещё раз
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
