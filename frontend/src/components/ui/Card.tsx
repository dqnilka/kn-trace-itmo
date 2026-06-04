import type { HTMLAttributes } from 'react'

/** Карточка дизайн-системы: острые углы, хайрлайн-бордер. */
export default function Card({
  framed = false,
  className = '',
  children,
  ...rest
}: { framed?: boolean } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card ${framed ? 'card-framed' : ''} ${className}`} {...rest}>
      {children}
    </div>
  )
}
