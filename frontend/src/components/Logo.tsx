/**
 * Логотип FinUplift — знак «подъёма»: восходящие столбцы и стрелка вверх.
 * Сдержанно и премиально, в тон острому дизайн-языку.
 */
export default function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label="FinUplift"
    >
      <rect x="2" y="2" width="60" height="60" rx="8" fill="#1c1b1a" />
      <rect x="14" y="40" width="7" height="10" fill="#ffffff" opacity="0.5" />
      <rect x="25" y="33" width="7" height="17" fill="#ffffff" opacity="0.72" />
      <rect x="36" y="24" width="7" height="26" fill="#c96442" />
      {/* стрелка-подъём */}
      <path
        d="M18 33 L39 18"
        stroke="#c96442"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <path
        d="M31 17 L40 17 L40 26"
        stroke="#c96442"
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  )
}
