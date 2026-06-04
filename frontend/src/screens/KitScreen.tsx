import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Field from '../components/ui/Field'
import { Skeleton, TheorySkeleton } from '../components/ui/Skeleton'
import BrandLoader from '../components/ui/BrandLoader'
import Logo from '../components/Logo'

/** Витрина дизайн-системы FinUplift — открывается по ?kit=1. */
export default function KitScreen() {
  const swatches: [string, string][] = [
    ['--bg', 'фон'],
    ['--bg-2', 'поверхность'],
    ['--bg-3', 'бежевый'],
    ['--fg', 'чернила'],
    ['--accent', 'акцент'],
    ['--ok', 'успех'],
    ['--warn', 'внимание'],
    ['--err', 'ошибка'],
  ]
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark">
            <Logo size={40} />
          </div>
          <div className="brand-title">FinUplift · UI Kit</div>
        </div>
      </header>
      <div className="screen-body kit-body">
        <h2 className="kit-h">Цвета</h2>
        <div className="kit-swatches">
          {swatches.map(([v, label]) => (
            <div key={v} className="kit-swatch-item">
              <div className="kit-swatch" style={{ background: `var(${v})` }} />
              <div className="kit-swatch-label">{label}</div>
              <code>{v}</code>
            </div>
          ))}
        </div>

        <h2 className="kit-h">Типографика</h2>
        <Card framed className="kit-type">
          <h1 className="screen-title">Geologica Display H1</h1>
          <h2 className="theory-section-title">Заголовок секции</h2>
          <p>
            Inter body — основной текст. Острые углы, хайрлайн-бордеры,
            тёплая палитра. Спокойно и по делу.
          </p>
          <p className="meta">caption / meta — вспомогательный текст</p>
        </Card>

        <h2 className="kit-h">Кнопки</h2>
        <div className="kit-row">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
          <Button size="big">Big primary</Button>
        </div>

        <h2 className="kit-h">Поля</h2>
        <Card framed className="kit-fields">
          <Field label="Email" placeholder="you@example.com" />
          <Field label="Пароль" type="password" placeholder="минимум 6 символов" />
          <Field label="С ошибкой" placeholder="неверно" error="Что-то не так" />
        </Card>

        <h2 className="kit-h">Чипы</h2>
        <div className="kit-row">
          <span className="chip chip-soft">soft</span>
          <span className="chip chip-muted">muted</span>
          <span className="chip chip-ok">ok</span>
        </div>

        <h2 className="kit-h">Загрузка</h2>
        <Card framed>
          <BrandLoader label="Загружаем…" hint="Брендовый лоадер для ожиданий" />
        </Card>
        <Card framed style={{ marginTop: 12 }}>
          <TheorySkeleton />
        </Card>
        <div className="kit-row" style={{ marginTop: 12 }}>
          <Skeleton width={120} height={20} />
          <Skeleton width={80} height={20} />
          <Skeleton width={160} height={20} />
        </div>
      </div>
    </div>
  )
}
