/**
 * Набор собственных линейных иконок (без эмодзи). Stroke = currentColor,
 * острый минималистичный стиль в тон дизайн-языку FinUplift.
 */
export type IconName =
  | 'theory'
  | 'practice'
  | 'target'
  | 'search'
  | 'settings'
  | 'idea'
  | 'alert'
  | 'check'
  | 'layers'
  | 'doc'
  | 'chevron'
  | 'like'
  | 'dislike'

export default function Icon({
  name,
  size = 18,
  className = '',
}: {
  name: IconName
  size?: number
  className?: string
}) {
  const p = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.75,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className: `icon icon-${name} ${className}`,
    'aria-hidden': true,
  }
  switch (name) {
    case 'theory':
      return (
        <svg {...p}>
          <path d="M4 5h7v15H4z M20 5h-7v15h7z" />
          <path d="M4 5c0-1 7-1 7 0M20 5c0-1-7-1-7 0" />
        </svg>
      )
    case 'practice':
      return (
        <svg {...p}>
          <path d="M4 5h11v14H4z" />
          <path d="M8 10l2 2 4-4" />
          <path d="M18 9l3-3-2-2-3 3z" />
        </svg>
      )
    case 'target':
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3.5" />
          <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" />
        </svg>
      )
    case 'search':
      return (
        <svg {...p}>
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l5 5" />
        </svg>
      )
    case 'settings':
      return (
        <svg {...p}>
          <path d="M3 7h12M3 12h18M3 17h8" />
          <circle cx="18" cy="7" r="2.2" />
          <circle cx="14" cy="17" r="2.2" />
        </svg>
      )
    case 'idea':
      return (
        <svg {...p}>
          <path d="M9 17h6M10 20h4" />
          <path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.2 1 2.5h6c0-1.3.3-1.8 1-2.5A6 6 0 0 0 12 3z" />
        </svg>
      )
    case 'alert':
      return (
        <svg {...p}>
          <path d="M12 3l9 16H3z" />
          <path d="M12 10v4M12 17h.01" />
        </svg>
      )
    case 'check':
      return (
        <svg {...p}>
          <path d="M4 12l5 5L20 6" />
        </svg>
      )
    case 'layers':
      return (
        <svg {...p}>
          <path d="M12 3l9 5-9 5-9-5z" />
          <path d="M3 13l9 5 9-5" />
        </svg>
      )
    case 'doc':
      return (
        <svg {...p}>
          <path d="M6 3h8l4 4v14H6z" />
          <path d="M14 3v4h4M9 12h6M9 16h6" />
        </svg>
      )
    case 'chevron':
      return (
        <svg {...p}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      )
    case 'like':
      return (
        <svg {...p}>
          <path d="M7 10v10H4V10z" />
          <path d="M7 10l4-7c1.2 0 2 1 2 2.2L12 9h5.5c1.2 0 2 1 1.8 2.2l-1.2 7c-.15.9-.9 1.8-2 1.8H7" />
        </svg>
      )
    case 'dislike':
      return (
        <svg {...p}>
          <path d="M7 14V4H4v10z" />
          <path d="M7 14l4 7c1.2 0 2-1 2-2.2L12 15h5.5c1.2 0 2-1 1.8-2.2l-1.2-7C17.95 4.9 17.2 4 16 4H7" />
        </svg>
      )
  }
}
