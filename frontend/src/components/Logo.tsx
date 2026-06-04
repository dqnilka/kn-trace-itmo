/**
 * Логотип — сдержанный профессиональный знак: скруглённый квадрат с мотивом
 * роста знаний (восходящие ступени + точка-цель). Без «маскота», в тон
 * серьёзного продукта.
 */
export default function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label="Логотип"
    >
      <defs>
        <linearGradient id="lg-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#d8784f" />
          <stop offset="1" stopColor="#c96442" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#lg-g)" />
      {/* восходящие ступени */}
      <rect x="16" y="38" width="8" height="10" rx="2" fill="#ffffff" opacity="0.55" />
      <rect x="28" y="30" width="8" height="18" rx="2" fill="#ffffff" opacity="0.78" />
      <rect x="40" y="22" width="8" height="26" rx="2" fill="#ffffff" />
      {/* точка-цель */}
      <circle cx="44" cy="16" r="4" fill="#ffffff" />
    </svg>
  )
}
