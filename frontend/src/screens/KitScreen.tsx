import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Field from '../components/ui/Field'
import { Skeleton, TheorySkeleton } from '../components/ui/Skeleton'
import BrandLoader from '../components/ui/BrandLoader'
import MasteryRings from '../components/MasteryRings'
import ProgressRing from '../components/ui/ProgressRing'
import Icon, { type IconName } from '../components/ui/Icon'
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
          <h1 className="screen-title">Source Serif 4 — заголовок</h1>
          <h2 className="theory-section-title">Заголовок секции</h2>
          <p>
            Source Sans 3 — основной текст. Острые углы, хайрлайн-бордеры,
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

        <h2 className="kit-h">Кольца знаний (Главная / главы): нет данных · низкий · средний · высокий</h2>
        <div className="kit-row" style={{ gap: 22 }}>
          <ProgressRing value={0} tone="neutral" size={78} label="?" />
          <ProgressRing value={0.3} tone="accent" size={78} />
          <ProgressRing value={0.58} tone="warn" size={78} />
          <ProgressRing value={0.86} tone="ok" size={78} />
        </div>

        <h2 className="kit-h">Прогресс после занятия — рост / падение / без изменений</h2>
        <Card framed>
          <MasteryRings
            themes={[
              { label: 'Тема выросла', from: 0.45, to: 0.7 },
              { label: 'Тема просела', from: 0.6, to: 0.4 },
              { label: 'Без изменений', from: 0.5, to: 0.5 },
            ]}
            overall={{ label: 'Общий уровень', from: 0.52, to: 0.61 }}
          />
        </Card>

        <h2 className="kit-h">Иконки (свои, без эмодзи)</h2>
        <div className="kit-row" style={{ gap: 18, color: 'var(--fg)' }}>
          {(
            ['theory', 'practice', 'target', 'search', 'idea', 'alert', 'check', 'layers', 'doc', 'settings', 'chevron'] as IconName[]
          ).map((n) => (
            <span key={n} title={n} style={{ display: 'inline-flex' }}>
              <Icon name={n} size={22} />
            </span>
          ))}
        </div>

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
