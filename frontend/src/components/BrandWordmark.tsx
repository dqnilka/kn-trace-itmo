export default function BrandWordmark({
  className,
}: {
  className?: string
}) {
  const cls = ['brand-wordmark', className].filter(Boolean).join(' ')
  return (
    <span className={cls} aria-label="FINUPLIFT">
      <span>FIN</span>
      <span className="brand-wordmark-up">UP</span>
      <span>LIFT</span>
    </span>
  )
}
