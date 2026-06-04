/** Скелетон-плейсхолдер с shimmer-анимацией. */
export function Skeleton({
  width,
  height = 16,
  radius = 8,
  style,
}: {
  width?: number | string
  height?: number | string
  radius?: number
  style?: React.CSSProperties
}) {
  return (
    <span
      className="skeleton"
      style={{ width: width ?? '100%', height, borderRadius: radius, ...style }}
    />
  )
}

/** Готовый скелетон карточки теории (несколько строк + заголовок). */
export function TheorySkeleton() {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      <Skeleton width="55%" height={26} radius={10} />
      <Skeleton width="100%" />
      <Skeleton width="96%" />
      <Skeleton width="90%" />
      <Skeleton width="40%" height={20} radius={8} style={{ marginTop: 12 }} />
      <Skeleton width="100%" />
      <Skeleton width="93%" />
      <Skeleton width="70%" />
    </div>
  )
}
