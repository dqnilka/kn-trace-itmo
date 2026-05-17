import { loadUser } from '../state/user'

/**
 * Узлы r1-r4 диаграммы fsfr-user-flow v2.
 *
 * Финальный набор материалов перед реальным экзаменом ФСФР (НОК):
 *   • сертификат готовности (PDF mock — здесь просто кнопка-заглушка),
 *   • инструкция регистрации в НОК (документы, ссылка, стоимость),
 *   • шпаргалки с формулами (скачиваемый PDF mock),
 *   • чеклист дня экзамена (что взять, когда прийти).
 */

const REGISTRATION_STEPS = [
  'Зайти на сайт https://nok-cbr.ru и завести личный кабинет (email + СНИЛС).',
  'Загрузить скан паспорта (разворот с фото и страница с пропиской).',
  'Оплатить пошлину 4 500 ₽ за серию (Базовая бесплатна для членов СРО).',
  'Выбрать ближайшую дату из календаря — обычно есть слоты 2-3 раза в неделю.',
  'За день до — пройти проверку оборудования (камера, микрофон, экран).',
]

const CHECKLIST = [
  'Паспорт (обязательно — без него не пустят даже за 1 минуту до старта).',
  'СНИЛС (могут не спросить, но лучше иметь).',
  'Прийти за 30 минут — на регистрацию, фото, инструктаж.',
  'Бутылка воды 0.5л — без этикетки (можно пронести в зал).',
  'Никаких часов, гаджетов, бумаг — телефон сдают на ресепшн.',
  'Спокойный завтрак, не больше кофе чем обычно — не время для экспериментов.',
]

export default function RealExamPrepScreen({
  onBack,
  onExamDone,
}: {
  onBack: () => void
  onExamDone: () => void
}) {
  const user = loadUser()
  const today = new Date()
  const certDate = today.toLocaleDateString('ru-RU')

  const downloadCertificate = () => {
    // mock «выдачи PDF» — отдаём текстовый файл
    const body =
      `СЕРТИФИКАТ ГОТОВНОСТИ\n\n` +
      `Имя: ${user?.name ?? '—'}\n` +
      `Email: ${user?.email ?? '—'}\n` +
      `Дата выдачи: ${certDate}\n\n` +
      `Курс: Базовый экзамен ФСФР\n` +
      `Уровень mastery: 80%+ по всем главам\n` +
      `Пробные экзамены: 2/2 успешно\n\n` +
      `Документ носит информационный характер.\n` +
      `Удачи на экзамене!`
    const blob = new Blob([body], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Certificate_FSFR_${(user?.name ?? 'student').replace(/\s+/g, '_')}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const downloadCheatsheet = () => {
    const body =
      `ШПАРГАЛКА: ключевые формулы экзамена ФСФР\n\n` +
      `1. Доходность облигации к погашению (YTM)\n` +
      `   YTM ≈ (C + (F - P) / n) / ((F + P) / 2)\n\n` +
      `2. Купонный доход\n` +
      `   Купон = Номинал × Ставка купона × Период / 365\n\n` +
      `3. Маржинальные требования по фьючерсу\n` +
      `   Маржа = Контракт × Гарантийное обеспечение (ГО) % ...\n\n` +
      `(сокращённая мок-выдача)`
    const blob = new Blob([body], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'Cheatsheet_FSFR.txt'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="screen">
      <div className="screen-head">
        <button className="link-button" onClick={onBack}>
          ← на дашборд
        </button>
      </div>
      <div className="screen-body narrow">
        <h1 className="screen-title">Материалы экзамена</h1>
        <p className="screen-subtitle">
          Финальный пакет — сертификат, инструкция регистрации в НОК,
          формула-шпаргалка и чеклист дня экзамена.
        </p>

        <section className="outcome-section">
          <h2 className="section-title">1. Сертификат готовности</h2>
          <div className="prep-card">
            <div className="prep-card-emoji">🎓</div>
            <div className="prep-card-body">
              <div className="prep-card-title">
                {user?.name ?? 'Студент'} · готов к экзамену ({certDate})
              </div>
              <div className="prep-card-sub">
                Скачиваемый файл с твоими метриками — можно показать руководству
                или СРО как подтверждение подготовки. (MVP: отдаём текстом
                вместо PDF.)
              </div>
              <button className="pill pill-cta" onClick={downloadCertificate}>
                ⬇ Скачать сертификат
              </button>
            </div>
          </div>
        </section>

        <section className="outcome-section">
          <h2 className="section-title">2. Регистрация в НОК</h2>
          <ol className="outcome-plan">
            {REGISTRATION_STEPS.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
          <div className="prep-card" style={{ marginTop: 14 }}>
            <div className="prep-card-emoji">🔗</div>
            <div className="prep-card-body">
              <div className="prep-card-title">Ссылка для регистрации</div>
              <div className="prep-card-sub">
                <code>https://nok-cbr.ru/exam/fsfr-basic</code> ·{' '}
                <span className="muted">официальный сайт НОК</span>
              </div>
            </div>
          </div>
        </section>

        <section className="outcome-section">
          <h2 className="section-title">3. Шпаргалка с формулами</h2>
          <div className="prep-card">
            <div className="prep-card-emoji">📄</div>
            <div className="prep-card-body">
              <div className="prep-card-title">YTM, купонный доход, маржа, ГО</div>
              <div className="prep-card-sub">
                ~10 ключевых формул на одну страницу. Открой утром перед
                экзаменом, потом убери.
              </div>
              <button className="pill pill-cta" onClick={downloadCheatsheet}>
                ⬇ Скачать шпаргалку
              </button>
            </div>
          </div>
        </section>

        <section className="outcome-section">
          <h2 className="section-title">4. Чеклист дня экзамена</h2>
          <ul className="checklist">
            {CHECKLIST.map((item, i) => (
              <li key={i}>
                <input type="checkbox" /> <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <div className="actions-row" style={{ marginTop: 22 }}>
          <button className="pill pill-primary big" onClick={onExamDone}>
            Я сдал(а) экзамен (демо: открыть пост-экзамен) →
          </button>
        </div>
      </div>
    </div>
  )
}
