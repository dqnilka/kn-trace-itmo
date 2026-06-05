/**
 * Логотип FinUplift — восходящая линия-график со стрелкой (рост / uplift).
 * Минималистичный знак в один акцентный цвет, на прозрачном фоне — чисто
 * сидит рядом со словесным знаком в шапке.
 */
export default function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="FinUplift"
    >
      {/* восходящая линия */}
      <path
        d="M4 23 L13 16 L19 19 L28 8"
        stroke="var(--accent, #c96442)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* стрелка-наконечник */}
      <path
        d="M22 8 H28 V14"
        stroke="var(--accent, #c96442)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* базовая ось */}
      <path
        d="M4 27 H28"
        stroke="var(--fg, #1c1b1a)"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.25"
      />
    </svg>
  )
}
